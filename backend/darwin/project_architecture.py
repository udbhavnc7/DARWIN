"""Evidence-backed backend architecture extraction for any GitHub repository.

This module is deliberately read-only and static. It never imports, builds or
executes repository code, and it never invents a service that a source file does
not support. Facts carry the file that produced them; low-confidence readings
are returned as review notes instead of asserted architecture.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

MAX_FILES = 20_000
MAX_SOURCE_FILES = 2_500
MAX_READ_BYTES = 900_000
MAX_TEXT_BUDGET = 48 * 1024 * 1024

IGNORED_DIRS = {
    '.git', '.hg', '.svn', 'node_modules', 'vendor', 'dist', 'build', 'out',
    'target', '.venv', 'venv', 'env', '__pycache__', '.next', '.nuxt', '.svelte-kit',
    '.angular', '.turbo', '.parcel-cache', '.pytest_cache', '.mypy_cache', '.ruff_cache',
    '.gradle', '.idea', '.vscode', 'Pods', 'DerivedData', 'coverage', '.cache',
    'playwright-report', 'test-results', '.terraform', 'bin', 'obj',
}

LANGUAGES = {
    '.py': 'Python', '.pyi': 'Python', '.ts': 'TypeScript', '.tsx': 'TypeScript',
    '.js': 'JavaScript', '.jsx': 'JavaScript', '.mjs': 'JavaScript', '.cjs': 'JavaScript',
    '.go': 'Go', '.java': 'Java', '.kt': 'Kotlin', '.kts': 'Kotlin', '.rb': 'Ruby',
    '.php': 'PHP', '.rs': 'Rust', '.cs': 'C#', '.fs': 'F#', '.ex': 'Elixir',
    '.exs': 'Elixir', '.scala': 'Scala', '.swift': 'Swift', '.c': 'C', '.h': 'C/C++',
    '.cc': 'C++', '.cpp': 'C++', '.hpp': 'C++', '.sql': 'SQL',
}

TEXT_SUFFIXES = {
    *LANGUAGES, '.json', '.toml', '.yaml', '.yml', '.md', '.txt', '.ini', '.cfg',
    '.conf', '.env', '.example', '.xml', '.gradle', '.properties', '.prisma', '.graphql',
    '.gql', '.proto', '.sh', '.ps1', '.dockerfile', '.lock', '.tf', '.hcl', '.properties',
}

MANIFESTS = {
    'package.json', 'pyproject.toml', 'requirements.txt', 'setup.py', 'setup.cfg',
    'Pipfile', 'go.mod', 'pom.xml', 'build.gradle', 'build.gradle.kts', 'settings.gradle',
    'settings.gradle.kts', 'composer.json', 'Gemfile', 'Cargo.toml', 'mix.exs',
    'pubspec.yaml', 'Package.swift', 'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml',
    'compose.yml', 'compose.yaml', 'Procfile', 'railway.json', 'render.yaml', 'fly.toml',
    'vercel.json', 'netlify.toml', 'serverless.yml', 'serverless.yaml', 'Chart.yaml',
}

FRONTEND_SIGNALS = {
    'react', 'react-dom', 'vue', 'svelte', '@sveltejs/kit', 'solid-js', 'preact',
    'next', 'nuxt', '@angular/core', 'astro', 'gatsby', 'remix', '@remix-run/react',
    'vite', 'parcel', 'webpack', 'tailwindcss',
}

PYTHON_FRAMEWORKS = {
    'fastapi': 'FastAPI', 'flask': 'Flask', 'django': 'Django', 'starlette': 'Starlette',
    'aiohttp': 'aiohttp', 'tornado': 'Tornado', 'pyramid': 'Pyramid', 'litestar': 'Litestar',
    'sanic': 'Sanic', 'falcon': 'Falcon', 'quart': 'Quart', 'bottle': 'Bottle',
    'djangorestframework': 'Django REST Framework', 'strawberry-graphql': 'Strawberry GraphQL',
    'ariadne': 'Ariadne GraphQL', 'celery': 'Celery',
}

NODE_FRAMEWORKS = {
    'express': 'Express', 'fastify': 'Fastify', 'koa': 'Koa', 'hapi': 'Hapi',
    '@hapi/hapi': 'Hapi', '@nestjs/core': 'NestJS', 'hono': 'Hono', 'restify': 'Restify',
    'next': 'Next.js', 'nuxt': 'Nuxt', '@remix-run/node': 'Remix', 'apollo-server': 'Apollo Server',
    '@apollo/server': 'Apollo Server', 'graphql-yoga': 'GraphQL Yoga', 'trpc': 'tRPC',
    '@trpc/server': 'tRPC', 'socket.io': 'Socket.IO', 'ws': 'WebSocket',
}

GO_FRAMEWORKS = {
    'github.com/gin-gonic/gin': 'Gin', 'github.com/labstack/echo': 'Echo',
    'github.com/gofiber/fiber': 'Fiber', 'github.com/go-chi/chi': 'Chi',
    'github.com/gorilla/mux': 'Gorilla Mux', 'github.com/julienschmidt/httprouter': 'httprouter',
    'github.com/beego/beego': 'Beego', 'net/http': 'net/http',
}

JVM_FRAMEWORKS = {
    'spring-boot': 'Spring Boot', 'spring-web': 'Spring MVC', 'spring-webflux': 'Spring WebFlux',
    'micronaut': 'Micronaut', 'quarkus': 'Quarkus', 'ktor': 'Ktor', 'javalin': 'Javalin',
    'dropwizard': 'Dropwizard', 'jakarta.ws.rs': 'JAX-RS', 'javax.ws.rs': 'JAX-RS',
    'hibernate': 'Hibernate', 'spring-data-jpa': 'Spring Data JPA',
}

RUBY_FRAMEWORKS = {'rails': 'Rails', 'sinatra': 'Sinatra', 'hanami': 'Hanami', 'grape': 'Grape'}
PHP_FRAMEWORKS = {'laravel/framework': 'Laravel', 'symfony/framework-bundle': 'Symfony',
                  'slim/slim': 'Slim', 'cakephp/cakephp': 'CakePHP'}
RUST_FRAMEWORKS = {'actix-web': 'Actix Web', 'axum': 'Axum', 'rocket': 'Rocket',
                   'warp': 'Warp', 'poem': 'Poem', 'tide': 'Tide'}
DOTNET_FRAMEWORKS = {'Microsoft.AspNetCore': 'ASP.NET Core',
                     'Microsoft.EntityFrameworkCore': 'Entity Framework Core'}

DATASTORE_SIGNALS = {
    'PostgreSQL': ('postgres', 'postgresql', 'psycopg', 'asyncpg', 'pg', 'npgsql',
                   'gorm.io/driver/postgres', 'jdbc:postgresql', 'pgx'),
    'MySQL': ('mysql', 'mysql2', 'pymysql', 'mysqlclient', 'jdbc:mysql', 'mariadb'),
    'SQLite': ('sqlite', 'better-sqlite3', 'sqlite3', 'aiosqlite', 'jdbc:sqlite'),
    'MongoDB': ('mongodb', 'mongoose', 'pymongo', 'motor', 'mongoclient', 'spring-data-mongodb'),
    'Redis': ('redis', 'ioredis', 'redis-py', 'go-redis', 'stackexchange.redis'),
    'Elasticsearch': ('elasticsearch', '@elastic/elasticsearch'),
    'ClickHouse': ('clickhouse', '@clickhouse/client'),
    'Cassandra': ('cassandra', 'scylla'),
    'Neo4j': ('neo4j', 'neo4j-driver'),
    'DynamoDB': ('dynamodb', '@aws-sdk/client-dynamodb'),
    'Firestore': ('firestore', '@google-cloud/firestore', 'firebase/firestore'),
    'Supabase': ('supabase', '@supabase/supabase-js'),
}

CACHE_NAMES = {'Redis', 'Memcached', 'Elasticsearch'}
QUEUE_SIGNALS = {
    'Celery': ('celery',), 'RQ': ('rq',), 'Dramatiq': ('dramatiq',), 'Huey': ('huey',),
    'BullMQ': ('bullmq',), 'Bull': ('bull',), 'Bee-Queue': ('bee-queue',),
    'Sidekiq': ('sidekiq',), 'Resque': ('resque',), 'RabbitMQ': ('rabbitmq', 'amqplib', 'pika'),
    'Kafka': ('kafka', 'kafkajs', 'confluent-kafka'), 'SQS': ('sqs', '@aws-sdk/client-sqs'),
    'NATS': ('nats',), 'Temporal': ('temporal', '@temporalio/client'), 'Inngest': ('inngest',),
    'Cloud Tasks': ('cloud tasks', '@google-cloud/tasks'), 'pg-boss': ('pg-boss',),
}

AUTH_SIGNALS = {
    'JWT': ('jsonwebtoken', 'pyjwt', 'jose', 'passport-jwt', '@nestjs/jwt', 'jwt-decode'),
    'OAuth': ('passport-oauth', 'authlib', 'oauth2', 'oauthlib', 'openid-client'),
    'Sessions': ('express-session', 'django.contrib.sessions', 'flask-login', 'cookie-session'),
    'Firebase Auth': ('firebase/auth', 'firebase-admin/auth'),
    'Auth0': ('auth0', '@auth0/nextjs-auth0'),
    'Clerk': ('@clerk/nextjs', '@clerk/clerk-react'),
    'Supabase Auth': ('@supabase/auth-helpers', '@supabase/ssr'),
    'NextAuth / Auth.js': ('next-auth', '@auth/core'),
    'Keycloak': ('keycloak', 'keycloak-js'),
    'Spring Security': ('spring-security',),
    'Django auth': ('django.contrib.auth',),
}

EXTERNAL_SIGNALS = {
    'Stripe': ('stripe',), 'Twilio': ('twilio',), 'SendGrid': ('@sendgrid/mail', 'sendgrid'),
    'Resend': ('resend',), 'OpenAI': ('openai', 'langchain-openai'),
    'Anthropic': ('anthropic', '@anthropic-ai/sdk'), 'Google Gemini': ('@google/genai', 'google-generativeai'),
    'AWS S3': ('@aws-sdk/client-s3', 'boto3', 'aws-sdk'), 'Cloudinary': ('cloudinary',),
    'Slack': ('@slack/web-api', 'slack-sdk'), 'Discord': ('discord.js', 'discord.py'),
    'GitHub API': ('@octokit/rest', 'pygithub', 'github'), 'Hugging Face': ('@huggingface/inference', 'huggingface-hub'),
    'Pinecone': ('@pinecone-database/pinecone',), 'Mapbox': ('mapbox-gl',),
    'Google Maps': ('@googlemaps/js-api-loader', 'googlemaps'),
}

TEST_SIGNALS = {
    'pytest': ('pytest', 'pytest.ini', 'conftest.py'),
    'Vitest': ('vitest',), 'Jest': ('jest',), 'Mocha': ('mocha',),
    'Playwright': ('@playwright/test', 'playwright'), 'Cypress': ('cypress',),
    'Go test': ('*_test.go',), 'JUnit': ('junit', 'junit-jupiter'),
    'RSpec': ('rspec',), 'PHPUnit': ('phpunit/phpunit',), 'Cargo test': ('cargo test',),
    'xUnit': ('xunit',), 'NUnit': ('nunit',), 'ExUnit': ('exunit',),
}

ROUTE_PATTERNS: dict[str, list[tuple[str, str]]] = {
    'python': [
        (r'@\s*(?:app|router|bp|blueprint|api)\s*\.\s*(get|post|put|patch|delete|route|api_route)\s*\(\s*[\'"]([^\'"]+)',
         'decorator'),
        (r'\b(?:path|re_path)\s*\(\s*r?[\'"]([^\'"]*)[\'"]', 'django'),
        (r'@\s*(?:app|router|bp|blueprint|api)\s*\.\s*(get|post|put|patch|delete)\s*\(\s*[\'"]([^\'"]+)',
         'decorator'),
    ],
    'javascript': [
        (r'\b(?:app|router|server|fastify|api)\s*\.\s*(get|post|put|patch|delete|all|route)\s*\(\s*[\'"`]([^\'"`]+)',
         'call'),
        (r'@\s*(Get|Post|Put|Patch|Delete)\s*\(\s*[\'"]?([^\'")]*)', 'nestjs'),
        (r'\b(?:app|router|server)\.(get|post|put|patch|delete)\s*\(\s*[\'"`]([^\'"`]+)', 'call'),
    ],
    'go': [
        (r'\.\s*(GET|POST|PUT|PATCH|DELETE)\s*\(\s*"([^"]+)"', 'call'),
        (r'\b(?:HandleFunc|Handle)\s*\(\s*"([^"]+)"', 'handle'),
        (r'\.\s*(?:Get|Post|Put|Patch|Delete)\s*\(\s*"([^"]+)"', 'call'),
    ],
    'java': [
        (r'@\s*(Get|Post|Put|Patch|Delete|Request)Mapping\s*\(\s*(?:value\s*=\s*)?[\'"]?([^\'")\s]*)',
         'mapping'),
        (r'@\s*(GET|POST|PUT|PATCH|DELETE)\s*(?:\(\s*[\'"]([^\'"]*)', 'jaxrs'),
    ],
}

GATEWAY_SIGNALS = ('nginx', 'traefik', 'caddy', 'envoy', 'kong', 'haproxy')

HOTSPOT_COPY = {
    'n_plus_one': ('Possible N+1 query loop', 'A query is called inside a loop. This can turn one request into many database round trips.'),
    'blocking_io': ('Possible blocking I/O in a request handler', 'Synchronous file or network work runs in a handler that may be serving concurrent requests.'),
    'sync_external': ('External call on the request path', 'A third-party API is called inline. Slow or failed providers directly hold the request.'),
    'unbounded_list': ('List endpoint may be unbounded', 'A list query has no visible pagination limit. Large tables can return too much data.'),
    'missing_cache': ('Repeated read path with no cache detected', 'Several read routes exist, but no cache dependency was found in the source.'),
    'missing_queue': ('Multiple outbound calls with no queue detected', 'Outbound work is not isolated behind a queue, so provider latency reaches users.'),
    'no_migrations': ('Models exist without a migration path', 'Data models were found, but no migrations directory or migration tool was detected.'),
    'no_health': ('No health endpoint detected', 'The service exposes routes but no obvious health or readiness probe.'),
    'no_tests': ('No test suite detected', 'A non-trivial source tree has no recognised test files.'),
    'no_auth': ('No authentication mechanism detected', 'Mutating routes exist, but no auth library or session mechanism was found. Confirm they are intentionally public.'),
    'no_pool': ('Database pooling is not visible', 'A database is used, but no pool or connection-limit configuration was found.'),
}


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _line(text: str, offset: int) -> int:
    return text.count('\n', 0, offset) + 1


def _snippet(text: str, offset: int, width: int = 140) -> str:
    start = max(0, offset - 40)
    end = min(len(text), offset + width)
    return ' '.join(text[start:end].split())


@dataclass
class SourceTree:
    root: Path
    files: list[str] = field(default_factory=list)
    texts: dict[str, str] = field(default_factory=dict)
    _budget: int = MAX_TEXT_BUDGET

    @classmethod
    def scan(cls, root: Path) -> 'SourceTree':
        tree = cls(root=root)
        count = 0
        for current, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(name for name in dirs if name not in IGNORED_DIRS)
            for name in sorted(names):
                path = Path(current) / name
                if path.is_symlink() or not path.is_file():
                    continue
                count += 1
                if count > MAX_FILES:
                    return tree
                tree.files.append(_rel(path, root))
        return tree

    def text(self, relative: str) -> str:
        if relative in self.texts:
            return self.texts[relative]
        path = self.root / relative
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in MANIFESTS:
            return ''
        try:
            if path.stat().st_size > MAX_READ_BYTES or self._budget <= 0:
                return ''
            raw = path.read_bytes()
        except OSError:
            return ''
        self._budget -= len(raw)
        value = raw.decode('utf-8', errors='replace')
        self.texts[relative] = value
        return value

    def matching(self, suffixes: Iterable[str] | None = None,
                 names: Iterable[str] | None = None, limit: int = MAX_SOURCE_FILES) -> list[str]:
        suffix_set = {item.lower() for item in (suffixes or ())}
        name_set = set(names or ())
        selected = []
        for relative in self.files:
            suffix = Path(relative).suffix.lower()
            if suffix_set and suffix not in suffix_set:
                continue
            if name_set and Path(relative).name not in name_set:
                continue
            selected.append(relative)
            if len(selected) >= limit:
                break
        return selected

    def json(self, relative: str) -> dict:
        value = self.text(relative)
        if not value:
            return {}
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}


def _dep_key(value: str) -> str:
    return value.strip().lower().removeprefix('@').replace('_', '-')


def _signal_match(needle: str, dependency: str) -> bool:
    """Exact matches are safe; a short substring such as 'pg' is not evidence."""
    needle = _dep_key(needle)
    dependency = _dep_key(dependency)
    return dependency == needle or (len(needle) >= 4 and needle in dependency)


def _normalise_dependencies(values: Iterable[str]) -> set[str]:
    result = set()
    for value in values:
        text = value.strip().lower()
        if not text:
            continue
        text = re.split(r'[<>=!~;\[(\s]', text, 1)[0]
        text = _dep_key(text)
        if text:
            result.add(text)
    return result


def _package_dependencies(tree: SourceTree, relative: str) -> set[str]:
    data = tree.json(relative)
    values: list[str] = []
    for key in ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies'):
        block = data.get(key)
        if isinstance(block, dict):
            values.extend(block.keys())
    return _normalise_dependencies(values)


def _manifest_dependencies(tree: SourceTree, relative: str) -> set[str]:
    name = Path(relative).name
    text = tree.text(relative)
    if not text:
        return set()
    if name == 'package.json':
        return _package_dependencies(tree, relative)
    values: list[str] = []
    if name == 'pyproject.toml':
        try:
            import tomllib
            data = tomllib.loads(text)
            project = data.get('project') or {}
            values.extend(project.get('dependencies') or [])
            poetry = ((data.get('tool') or {}).get('poetry') or {})
            values.extend((poetry.get('dependencies') or {}).keys())
            values.extend((poetry.get('dev-dependencies') or {}).keys())
        except (ValueError, ImportError):
            values.extend(re.findall(r'["\']([A-Za-z0-9_.-]+)\s*(?:[<>=!~;\[]|["\'])', text))
    elif name in ('requirements.txt', 'requirements-dev.txt', 'Pipfile'):
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith(('#', '-', 'http')):
                values.append(line)
    elif name == 'go.mod':
        values.extend(re.findall(r'^\s*([A-Za-z0-9_.\-/]+\.[A-Za-z]{2,}/[^\s]+)\s+v', text, re.M))
        values.extend(re.findall(r'^\s*(net/http)\b', text, re.M))
    elif name in ('pom.xml', 'build.gradle', 'build.gradle.kts'):
        values.extend(re.findall(r'<artifactId>([^<]+)</artifactId>', text))
        values.extend(re.findall(r'(?:implementation|api|compile)\s*\(?\s*[\'"]([^\'"]+)', text))
    elif name == 'composer.json':
        data = tree.json(relative)
        for key in ('require', 'require-dev'):
            block = data.get(key)
            if isinstance(block, dict):
                values.extend(block.keys())
    elif name == 'Gemfile':
        values.extend(re.findall(r'^\s*gem\s+[\'"]([^\'"]+)', text, re.M))
    elif name == 'Cargo.toml':
        try:
            import tomllib
            data = tomllib.loads(text)
            for key in ('dependencies', 'dev-dependencies'):
                block = data.get(key) or {}
                values.extend(block.keys())
        except (ValueError, ImportError):
            values.extend(re.findall(r'^([A-Za-z0-9_-]+)\s*=', text, re.M))
    elif name.endswith('.csproj'):
        values.extend(re.findall(r'<PackageReference\s+Include="([^"]+)"', text))
        values.extend(re.findall(r'<Project\s+Sdk="([^"]+)"', text))
    elif name == 'mix.exs':
        values.extend(re.findall(r'\{:([a-z0-9_]+)', text))
    return _normalise_dependencies(values)


def _all_dependencies(tree: SourceTree, manifests: list[str]) -> dict[str, set[str]]:
    return {relative: _manifest_dependencies(tree, relative) for relative in manifests}


def _count_languages(tree: SourceTree) -> list[dict]:
    counts: dict[str, int] = {}
    evidence: dict[str, str] = {}
    for relative in tree.files:
        language = LANGUAGES.get(Path(relative).suffix.lower())
        if not language:
            continue
        counts[language] = counts.get(language, 0) + 1
        evidence.setdefault(language, relative)
    return [{'language': language, 'files': count, 'evidence': evidence[language]}
            for language, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]


def _frontend_detected(tree: SourceTree, dependencies: dict[str, set[str]]) -> tuple[bool, list[str]]:
    hits = []
    evidence = []
    for relative, deps in dependencies.items():
        overlap = {signal for signal in FRONTEND_SIGNALS
                   if any(_signal_match(signal, dep) for dep in deps)}
        if overlap:
            hits.extend(sorted(overlap))
            evidence.append(relative)
    if any(Path(relative).suffix.lower() in ('.tsx', '.jsx', '.vue', '.svelte')
           for relative in tree.files):
        hits.append('component files')
    return bool(hits), sorted(set(evidence))[:4]


def _entry_points(tree: SourceTree, service_path: str, language: str) -> list[str]:
    candidates = {
        'Python': ('main.py', 'app.py', 'asgi.py', 'wsgi.py', 'manage.py', 'server.py',
                   'app/main.py', 'src/main.py', 'src/app.py'),
        'JavaScript': ('server.ts', 'server.js', 'index.ts', 'index.js', 'src/server.ts',
                       'src/index.ts', 'src/server.js', 'src/index.js', 'app.js', 'main.js'),
        'Go': ('main.go', 'cmd/server/main.go', 'cmd/api/main.go', 'cmd/main.go'),
        'Java': ('src/main/java/Application.java', 'src/main/kotlin/Application.kt'),
        'Kotlin': ('src/main/kotlin/Application.kt', 'src/main/kotlin/Main.kt'),
        'Ruby': ('config.ru', 'app.rb', 'config/application.rb'),
        'PHP': ('public/index.php', 'artisan'),
        'Rust': ('src/main.rs',),
        'C#': ('Program.cs', 'Startup.cs'),
        'Elixir': ('lib/application.ex', 'mix.exs'),
    }.get(language, ())
    prefix = service_path.rstrip('/') + '/' if service_path else ''
    found = []
    for candidate in candidates:
        relative = f'{prefix}{candidate}'
        if relative in tree.files:
            found.append(relative)
    if language == 'Go':
        found.extend(relative for relative in tree.files
                     if relative.startswith(prefix) and relative.endswith('main.go')
                     and relative not in found)[:3]
    return found[:6]


def _nextjs_methods(text: str) -> list[str]:
    methods = set(re.findall(
        r'export\s+(?:async\s+)?(?:function|const)\s+(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b',
        text))
    return sorted(methods)


def _route_hits(tree: SourceTree, service_path: str, language: str,
                limit: int = 240) -> list[dict]:
    route_key = 'javascript' if 'JavaScript' in language or 'TypeScript' in language else \
        'python' if 'Python' in language else 'go' if language == 'Go' else \
        'java' if language in ('Java', 'Kotlin', 'Java/Kotlin') else ''
    patterns = ROUTE_PATTERNS.get(route_key, [])
    if not patterns:
        return []
    prefix = service_path.rstrip('/') + '/' if service_path else ''
    suffixes = {'.py'} if route_key == 'python' else \
        {'.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'} if route_key == 'javascript' else \
        {'.go'} if route_key == 'go' else {'.java', '.kt'}
    results: list[dict] = []
    seen = set()
    for relative in tree.matching(suffixes=suffixes):
        if prefix and not relative.startswith(prefix):
            continue
        text = tree.text(relative)
        if not text:
            continue
        for pattern, kind in patterns:
            for match in re.finditer(pattern, text):
                groups = [group for group in match.groups() if group is not None]
                if not groups:
                    continue
                method = 'ANY'
                path = ''
                if kind in ('decorator', 'call', 'mapping'):
                    if len(groups) >= 2:
                        method, path = groups[0].upper(), groups[1]
                    else:
                        path = groups[0]
                elif kind == 'django':
                    path = groups[0]
                elif kind == 'handle':
                    path = groups[0]
                elif kind == 'nestjs':
                    method, path = groups[0].upper(), (groups[1] if len(groups) > 1 else '')
                elif kind == 'jaxrs':
                    method, path = groups[0].upper(), (groups[1] if len(groups) > 1 else '')
                if method in ('ROUTE', 'REQUEST', 'ANY'):
                    method = 'ANY'
                key = (method, path, relative, _line(text, match.start()))
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    'method': method,
                    'path': path or '/',
                    'file': relative,
                    'line': _line(text, match.start()),
                    'service_path': service_path,
                    'snippet': _snippet(text, match.start()),
                })
                if len(results) >= limit:
                    return results
    # File-based Next.js / Remix routes are real routes even without a decorator.
    for relative in tree.files:
        if prefix and not relative.startswith(prefix):
            continue
        match = re.search(r'(?:^|/)(?:app|src/app)/(.*)/route\.(?:js|jsx|ts|tsx)$', relative)
        if match:
            route_path = '/' + match.group(1).replace('/route', '')
            methods = _nextjs_methods(tree.text(relative)) or ['ANY']
            for method in methods:
                results.append({'method': method, 'path': route_path, 'file': relative,
                                'line': 1, 'service_path': service_path,
                                'snippet': 'Next.js route handler'})
        match = re.search(r'(?:^|/)(?:pages|src/pages)/api/(.*)\.(?:js|jsx|ts|tsx)$', relative)
        if match:
            results.append({'method': 'ANY', 'path': '/api/' + match.group(1),
                            'file': relative, 'line': 1, 'service_path': service_path,
                            'snippet': 'Next.js pages API route'})
        if len(results) >= limit:
            break
    return results[:limit]


def _has_route(routes: list[dict], fragment: str) -> bool:
    return any(fragment.lower() in str(route.get('path', '')).lower() for route in routes)


def _match_signals(dependencies: dict[str, set[str]], table: dict[str, tuple[str, ...]],
                   evidence_limit: int = 4) -> list[dict]:
    found: dict[str, list[str]] = {}
    for relative, deps in dependencies.items():
        for label, signals in table.items():
            for signal in signals:
                needle = signal.lower()
                if any(_signal_match(needle, dep) for dep in deps):
                    found.setdefault(label, []).append(relative)
                    break
    results = []
    for label, files in sorted(found.items()):
        results.append({'name': label, 'evidence': sorted(set(files))[:evidence_limit]})
    return results


def _compose_services(tree: SourceTree) -> list[dict]:
    services = []
    for relative in tree.files:
        if Path(relative).name not in ('docker-compose.yml', 'docker-compose.yaml',
                                       'compose.yml', 'compose.yaml'):
            continue
        text = tree.text(relative)
        if not text:
            continue
        for match in re.finditer(r'^\s{2,6}([A-Za-z0-9_.-]+):\s*$', text, re.M):
            name = match.group(1)
            following = text[match.end():match.end() + 500]
            image = re.search(r'image:\s*([^\s#]+)', following)
            if image:
                services.append({'name': name, 'image': image.group(1), 'file': relative})
    return services


def _deployment(tree: SourceTree) -> list[dict]:
    found = []
    markers = {
        'Dockerfile': 'Docker image', 'docker-compose.yml': 'Docker Compose',
        'docker-compose.yaml': 'Docker Compose', 'compose.yml': 'Docker Compose',
        'compose.yaml': 'Docker Compose', 'Procfile': 'Procfile process',
        'railway.json': 'Railway', 'render.yaml': 'Render', 'fly.toml': 'Fly.io',
        'vercel.json': 'Vercel', 'netlify.toml': 'Netlify', 'serverless.yml': 'Serverless',
        'serverless.yaml': 'Serverless', 'Chart.yaml': 'Helm chart',
    }
    for relative in tree.files:
        name = Path(relative).name
        if name in markers:
            found.append({'name': markers[name], 'evidence': relative})
    for relative in tree.files:
        if relative.endswith('.tf'):
            found.append({'name': 'Terraform', 'evidence': relative})
            break
    for relative in tree.files:
        if relative.startswith('.github/workflows/') and relative.endswith(('.yml', '.yaml')):
            found.append({'name': 'GitHub Actions', 'evidence': relative})
            break
    for relative in tree.files:
        if re.search(r'(?:^|/)(?:k8s|kubernetes|deploy)/', relative) and relative.endswith(('.yml', '.yaml')):
            found.append({'name': 'Kubernetes manifests', 'evidence': relative})
            break
    return found[:12]


def _tests(tree: SourceTree, dependencies: dict[str, set[str]], services: list[dict],
           frontend_evidence: list[str]) -> dict:
    files = [relative for relative in tree.files
             if re.search(r'(?:^|/)(?:test|tests|__tests__|spec)/|(?:^|/)(?:test_[^/]+\.py|[^/]+_test\.go|[^/]+\.(?:test|spec)\.(?:js|jsx|ts|tsx))$',
                          relative)]
    roots = [service['path'].rstrip('/') + '/' for service in services if service['path']]
    if not roots and frontend_evidence:
        roots = [str(Path(frontend_evidence[0]).parent.as_posix()).rstrip('/') + '/']
    if roots and roots != ['/']:
        files = [relative for relative in files
                 if any(relative.startswith(root) for root in roots)]
    frameworks = [item['name'] for item in _match_signals(dependencies, TEST_SIGNALS)]
    if any(relative.endswith('.py') and 'test' in Path(relative).name for relative in files):
        frameworks = sorted(set(frameworks) | {'pytest'})
    return {'frameworks': frameworks, 'file_count': len(files),
            'evidence': files[:4]}


def _models(tree: SourceTree) -> list[dict]:
    results = []
    patterns = [
        (r'^\s*model\s+([A-Za-z0-9_]+)\s*\{', 'Prisma'),
        (r'class\s+([A-Za-z0-9_]+)\s*\(\s*models\.Model\s*\)', 'Django ORM'),
        (r'class\s+([A-Za-z0-9_]+)\s*\(\s*(?:Base|db\.Model)\s*\)', 'SQLAlchemy'),
        (r'@Entity\s*(?:\([^)]*\))?\s*(?:public\s+)?class\s+([A-Za-z0-9_]+)', 'JPA / Hibernate'),
        (r'class\s+([A-Za-z0-9_]+)\s*<\s*ApplicationRecord', 'ActiveRecord'),
        (r'@Entity\(\)[\s\S]{0,200}?class\s+([A-Za-z0-9_]+)', 'TypeORM'),
    ]
    for relative in tree.matching(suffixes={'.prisma', '.py', '.java', '.kt', '.rb', '.ts'}):
        text = tree.text(relative)
        if not text:
            continue
        for pattern, framework in patterns:
            for match in re.finditer(pattern, text, re.M):
                results.append({'name': match.group(1), 'framework': framework,
                                'file': relative, 'line': _line(text, match.start())})
                if len(results) >= 80:
                    return results
    return results


def _migrations(tree: SourceTree) -> list[str]:
    markers = ('migrations/', 'alembic/', 'prisma/migrations/', 'db/migrate/',
               'src/main/resources/db/migration/', 'flyway', 'liquibase')
    return [relative for relative in tree.files
            if any(marker in relative for marker in markers)][:4]


def _background_jobs(tree: SourceTree, dependencies: dict[str, set[str]]) -> list[dict]:
    queues = _match_signals(dependencies, QUEUE_SIGNALS)
    files = [relative for relative in tree.files
             if re.search(r'(?:^|/)(?:worker|workers|consumer|consumers|jobs|tasks)\.(?:py|js|ts|go|rb)$',
                          relative)]
    return [{'name': item['name'], 'evidence': item['evidence']} for item in queues] + [
        {'name': 'Worker file', 'evidence': relative} for relative in files[:4]
    ]


def _manifest_name(tree: SourceTree, relative: str, fallback: str) -> str:
    if Path(relative).name == 'package.json':
        value = tree.json(relative).get('name')
        if isinstance(value, str) and value.strip():
            return value.strip().replace('@', '').replace('/', '-')[:60]
    if Path(relative).name == 'pyproject.toml':
        import re as _re
        match = _re.search(r'^\s*name\s*=\s*["\']([^"\']+)', tree.text(relative), _re.M)
        if match:
            return match.group(1)[:60]
    return fallback or 'app'


def _source_has(tree: SourceTree, prefix: str, suffixes: set[str], pattern: str) -> str:
    scope = prefix.rstrip('/') + '/' if prefix else ''
    for relative in tree.matching(suffixes=suffixes):
        if scope and not relative.startswith(scope):
            continue
        if re.search(pattern, tree.text(relative), re.M):
            return relative
    return ''


def _service_candidates(tree: SourceTree, dependencies: dict[str, set[str]]) -> list[dict]:
    languages = _count_languages(tree)
    primary = languages[0]['language'] if languages else ''
    manifests = [relative for relative in tree.files if Path(relative).name in MANIFESTS]
    services = []

    def add(path: str, name: str, language: str, framework: str, entry: list[str],
            evidence: list[str], kind: str = 'http_api') -> None:
        if any(item['path'] == path for item in services):
            return
        services.append({'name': name, 'path': path, 'language': language,
                         'framework': framework, 'kind': kind,
                         'entry_points': entry, 'evidence': evidence[:6]})

    for relative in manifests:
        name = Path(relative).name
        directory = str(Path(relative).parent.as_posix())
        directory = '' if directory == '.' else directory
        deps = dependencies.get(relative, set())
        if name == 'package.json':
            frameworks = [label for signal, label in NODE_FRAMEWORKS.items()
                          if any(_signal_match(signal, dep) for dep in deps)]
            scope = directory.rstrip('/') + '/' if directory else ''
            api_routes = any(
                (not scope or item.startswith(scope)) and (
                    re.search(r'(?:^|/)(?:app|src/app)/api/.*/route\.(?:js|ts)$', item)
                    or re.search(r'(?:^|/)(?:pages|src/pages)/api/.*\.(?:js|ts)$', item))
                for item in tree.files)
            if frameworks or api_routes:
                entry = _entry_points(tree, directory, 'JavaScript')
                has_server = bool(entry or api_routes)
                if has_server:
                    add(directory, _manifest_name(tree, relative, Path(directory).name or 'app'),
                        'JavaScript/TypeScript', frameworks[0] if frameworks else 'Node.js HTTP',
                        entry, [relative], 'fullstack' if 'Next.js' in frameworks else 'http_api')
        elif name in ('pyproject.toml', 'requirements.txt', 'Pipfile'):
            frameworks = [label for signal, label in PYTHON_FRAMEWORKS.items()
                          if any(_signal_match(signal, dep) for dep in deps)]
            if frameworks:
                entry = _entry_points(tree, directory, 'Python')
                route_file = _source_has(tree, directory, {'.py'},
                                         r'@\s*(?:app|router|bp|blueprint|api)\s*\.\s*'
                                         r'(?:get|post|put|patch|delete|route|api_route)\s*\(')
                if entry or route_file:
                    add(directory, _manifest_name(tree, relative, Path(directory).name or 'app'),
                        'Python', frameworks[0], entry or [route_file], [relative], 'http_api')
        elif name == 'go.mod':
            frameworks = [label for signal, label in GO_FRAMEWORKS.items()
                          if any(_signal_match(signal, dep) for dep in deps)]
            entry = _entry_points(tree, directory, 'Go')
            route_file = _source_has(tree, directory, {'.go'},
                                     r'\.\s*(?:GET|POST|PUT|PATCH|DELETE|HandleFunc|Handle)\s*\(')
            if frameworks and (entry or route_file):
                add(directory, Path(directory).name or 'app', 'Go',
                    frameworks[0] if frameworks else 'Go HTTP',
                    entry or [route_file], [relative], 'http_api')
        elif name in ('pom.xml', 'build.gradle', 'build.gradle.kts'):
            frameworks = [label for signal, label in JVM_FRAMEWORKS.items()
                          if any(_signal_match(signal, dep) for dep in deps)]
            if frameworks:
                entry = _entry_points(tree, directory, 'Java')
                add(directory, Path(directory).name or 'app', 'Java/Kotlin',
                    frameworks[0], entry, [relative], 'http_api')
        elif name == 'composer.json':
            frameworks = [label for signal, label in PHP_FRAMEWORKS.items()
                          if any(_signal_match(signal, dep) for dep in deps)]
            if frameworks:
                add(directory, Path(directory).name or 'app', 'PHP',
                    frameworks[0], _entry_points(tree, directory, 'PHP'), [relative], 'http_api')
        elif name == 'Gemfile':
            frameworks = [label for signal, label in RUBY_FRAMEWORKS.items()
                          if any(_signal_match(signal, dep) for dep in deps)]
            if frameworks:
                add(directory, Path(directory).name or 'app', 'Ruby',
                    frameworks[0], _entry_points(tree, directory, 'Ruby'), [relative], 'http_api')
        elif name == 'Cargo.toml':
            frameworks = [label for signal, label in RUST_FRAMEWORKS.items()
                          if any(_signal_match(signal, dep) for dep in deps)]
            if frameworks:
                add(directory, Path(directory).name or 'app', 'Rust',
                    frameworks[0], _entry_points(tree, directory, 'Rust'), [relative], 'http_api')
        elif name.endswith('.csproj'):
            frameworks = [label for signal, label in DOTNET_FRAMEWORKS.items()
                          if any(_signal_match(signal, dep) for dep in deps)]
            if frameworks:
                add(directory, Path(directory).name or 'app', 'C#',
                    frameworks[0], _entry_points(tree, directory, 'C#'), [relative], 'http_api')

    # A root package may live above nested service manifests. Keep only the
    # shallowest manifest for the same directory and cap the list.
    unique = {}
    for service in services:
        unique.setdefault(service['path'], service)
    if not unique and primary in ('Python', 'JavaScript', 'TypeScript', 'Go', 'Java', 'Kotlin',
                                  'Ruby', 'PHP', 'Rust', 'C#'):
        entry = _entry_points(tree, '', primary)
        if entry:
            unique[''] = {'name': Path(tree.root).name or 'app', 'path': '',
                          'language': primary, 'framework': 'Unclassified service',
                          'kind': 'http_api', 'entry_points': entry,
                          'evidence': entry[:2]}
    return list(unique.values())[:12]


def _pick_primary_framework(service: dict, dependencies: dict[str, set[str]]) -> str:
    relative = service.get('evidence', [''])[0]
    deps = dependencies.get(relative, set())
    table = PYTHON_FRAMEWORKS if service['language'] == 'Python' else \
        NODE_FRAMEWORKS if service['language'] == 'JavaScript/TypeScript' else \
        GO_FRAMEWORKS if service['language'] == 'Go' else \
        JVM_FRAMEWORKS if service['language'] == 'Java/Kotlin' else \
        RUBY_FRAMEWORKS if service['language'] == 'Ruby' else \
        PHP_FRAMEWORKS if service['language'] == 'PHP' else \
        RUST_FRAMEWORKS if service['language'] == 'Rust' else DOTNET_FRAMEWORKS
    labels = [label for signal, label in table.items()
              if any(_signal_match(signal, dep) for dep in deps)]
    return labels[0] if labels else service.get('framework', 'Unclassified service')


def _backend_files(tree: SourceTree, services: list[dict], suffixes: set[str]) -> list[str]:
    prefixes = tuple(service['path'].rstrip('/') + '/' for service in services if service['path'])
    entry_points = {item for service in services for item in service.get('entry_points', [])}
    fragments = ('/api/', '/routes/', '/controllers/', '/handlers/', '/server/', '/workers/',
                 '/consumers/', '/jobs/', '/tasks/', '/services/', '/lib/', '/src/lib/',
                 '/src/server', 'server.ts', 'server.js', 'main.py', 'app.py', 'manage.py')
    selected = []
    for relative in tree.matching(suffixes=suffixes):
        if prefixes and not any(relative.startswith(prefix) for prefix in prefixes):
            continue
        lowered = '/' + relative.lower()
        if relative in entry_points or any(fragment in lowered for fragment in fragments):
            selected.append(relative)
    return selected[:800]


def _source_signals(tree: SourceTree, services: list[dict], patterns: dict[str, tuple[str, ...]],
                    suffixes: set[str]) -> list[dict]:
    found: dict[str, list[dict]] = {}
    for relative in _backend_files(tree, services, suffixes):
        text = tree.text(relative)
        if not text:
            continue
        lowered = text.lower()
        for label, needles in patterns.items():
            if label in found:
                continue
            for needle in needles:
                index = lowered.find(needle.lower())
                if index >= 0:
                    found[label] = [{'file': relative, 'line': _line(text, index)}]
                    break
    return [{'name': label, 'evidence': [item['file'] for item in entries[:2]],
             'locations': entries[:2]}
            for label, entries in sorted(found.items())]


SOURCE_AUTH_PATTERNS = {
    'Cookie session': ('cookies()', 'next/headers', 'request.cookies', 'cookie-session',
                       'res.cookie(', 'req.cookies'),
    'JWT / bearer token': ('authorization', 'bearer ', 'jwt.verify', 'jwt.sign', 'jsonwebtoken'),
    'Password hashing': ('bcrypt', 'argon2', 'scrypt', 'password_hash', 'pbkdf2'),
    'Session store': ('express-session', 'req.session', 'sessionid', 'session_store'),
    'Admin login guard': ('admin_session', 'requireadmin', 'require_admin', 'isauthenticated',
                          'is_authenticated', 'login_required', 'isauthorized'),
}

SOURCE_EXTERNAL_PATTERNS = {
    'Resend': ('api.resend.com',), 'GitHub API': ('api.github.com',),
    'OpenAI': ('api.openai.com',), 'Google Gemini': ('generativelanguage.googleapis.com',),
    'Anthropic': ('api.anthropic.com',), 'Stripe': ('api.stripe.com',),
    'Twilio': ('api.twilio.com',), 'SendGrid': ('api.sendgrid.com',),
    'Cloudinary': ('api.cloudinary.com',), 'Slack': ('slack.com/api',),
    'Mapbox': ('api.mapbox.com',), 'Google Maps': ('maps.googleapis.com',),
    'Pinecone': ('api.pinecone.io',), 'Hugging Face': ('huggingface.co',),
    'AWS S3': ('s3.amazonaws.com',),
}


def _merge_signals(base: list[dict], extra: list[dict]) -> list[dict]:
    merged = {item['name']: {'name': item['name'],
                             'evidence': list(item.get('evidence', []))}
              for item in base}
    for item in extra:
        current = merged.setdefault(item['name'], {'name': item['name'], 'evidence': []})
        current['evidence'] = sorted(set(current['evidence']) | set(item.get('evidence', [])))
        if item.get('locations'):
            current['locations'] = item['locations']
    return [merged[name] for name in sorted(merged)]


def _detect_architecture(tree: SourceTree, services: list[dict], dependencies: dict[str, set[str]],
                         routes: list[dict], frontend: bool,
                         frontend_evidence: list[str]) -> dict:
    all_deps = set().union(*dependencies.values()) if dependencies else set()
    datastores = _match_signals(dependencies, DATASTORE_SIGNALS)
    for store in datastores:
        store['role'] = 'cache' if store['name'] in CACHE_NAMES else 'primary'
    queues = _match_signals(dependencies, QUEUE_SIGNALS)
    auth = _merge_signals(
        _match_signals(dependencies, AUTH_SIGNALS),
        _source_signals(tree, services, SOURCE_AUTH_PATTERNS, {'.py', '.js', '.jsx', '.ts', '.tsx'}),
    )
    external = _merge_signals(
        _match_signals(dependencies, EXTERNAL_SIGNALS),
        _source_signals(tree, services, SOURCE_EXTERNAL_PATTERNS, {'.py', '.js', '.jsx', '.ts', '.tsx'}),
    )
    deployment = _deployment(tree)
    tests = _tests(tree, dependencies, services, frontend_evidence)
    models = _models(tree)
    migrations = _migrations(tree)
    jobs = _background_jobs(tree, dependencies)

    compose = _compose_services(tree)
    for service in compose:
        image = service['image'].lower()
        for label, signals in DATASTORE_SIGNALS.items():
            if any(signal in image for signal in signals):
                if not any(item['name'] == label for item in datastores):
                    datastores.append({'name': label,
                                       'role': 'cache' if label in CACHE_NAMES else 'primary',
                                       'evidence': [service['file']]})
        for label, signals in QUEUE_SIGNALS.items():
            if any(signal in image for signal in signals):
                if not any(item['name'] == label for item in queues):
                    queues.append({'name': label, 'evidence': [service['file']]})

    gateway = next((name for name in GATEWAY_SIGNALS if any(name in item.lower() for item in tree.files)), '')
    nodes: list[dict] = []
    edges: list[dict] = []
    if frontend:
        nodes.append({'id': 'client', 'label': 'Client UI', 'kind': 'client',
                      'detail': 'Browser / app user interface', 'evidence': []})
    if gateway:
        nodes.append({'id': 'gateway', 'label': 'Gateway', 'kind': 'gateway',
                      'detail': gateway.title(), 'evidence': []})
    for index, service in enumerate(services):
        node_id = f'service-{index}'
        service['node_id'] = node_id
        nodes.append({'id': node_id, 'label': service['name'] or 'Service',
                      'kind': 'service', 'detail': f"{service['framework']} · {service['language']}",
                      'evidence': service['evidence'][:2]})
        if gateway:
            edges.append({'source': 'gateway', 'target': node_id, 'label': 'routes'})
        elif frontend:
            edges.append({'source': 'client', 'target': node_id, 'label': 'HTTP'})
    for index, store in enumerate(datastores):
        node_id = f'data-{index}'
        store['node_id'] = node_id
        nodes.append({'id': node_id, 'label': store['name'],
                      'kind': 'cache' if store['role'] == 'cache' else 'database',
                      'detail': 'Cache' if store['role'] == 'cache' else 'Primary data store',
                      'evidence': store['evidence'][:2]})
        for service in services:
            edges.append({'source': service.get('node_id', 'service-0'), 'target': node_id,
                          'label': 'cache' if store['role'] == 'cache' else 'reads/writes'})
    for index, queue in enumerate(queues):
        node_id = f'queue-{index}'
        queue['node_id'] = node_id
        nodes.append({'id': node_id, 'label': queue['name'], 'kind': 'queue',
                      'detail': 'Asynchronous work', 'evidence': queue['evidence'][:2]})
        for service in services:
            edges.append({'source': service.get('node_id', 'service-0'), 'target': node_id,
                          'label': 'publishes'})
    if jobs:
        nodes.append({'id': 'worker', 'label': 'Background worker', 'kind': 'worker',
                      'detail': f"{len(jobs)} worker signal(s)", 'evidence': [
                          item['evidence'][0] for item in jobs if item.get('evidence')][:3]})
        for queue in queues:
            edges.append({'source': queue.get('node_id', 'queue-0'), 'target': 'worker',
                          'label': 'consumes'})
        edges.append({'source': 'worker', 'target': 'data-0', 'label': 'writes'}) if datastores else None
    for index, item in enumerate(external[:5]):
        node_id = f'external-{index}'
        item['node_id'] = node_id
        nodes.append({'id': node_id, 'label': item['name'], 'kind': 'external',
                      'detail': 'Third-party API', 'evidence': item['evidence'][:2]})
        for service in services:
            edges.append({'source': service.get('node_id', 'service-0'), 'target': node_id,
                          'label': 'calls'})
    if frontend and not services:
        nodes.append({'id': 'browser-storage', 'label': 'Browser storage', 'kind': 'storage',
                      'detail': 'localStorage / IndexedDB', 'evidence': []})
        edges.append({'source': 'client', 'target': 'browser-storage', 'label': 'persists'})

    flow = []
    if frontend:
        flow.append('The visible client runs in a browser or app shell.')
    if services:
        flow.append(f"Requests reach {services[0]['name'] or 'the service'} through "
                    f"{'the gateway' if gateway else 'the client'}.")
        flow.append(f"The service uses {services[0]['framework']} and exposes "
                    f"{len(routes)} detected route(s).")
    if datastores:
        flow.append('Data is stored in ' + ', '.join(item['name'] for item in datastores) + '.')
    if queues or jobs:
        flow.append('Background work is queued or handled by a worker process.')
    if external:
        flow.append('Outbound calls go to ' + ', '.join(item['name'] for item in external[:4]) + '.')
    if not services and frontend:
        flow.append('No deployed server backend was found; the visible app is client-side.')

    return {
        'nodes': nodes,
        'edges': edges,
        'flow': flow,
        'gateway': gateway,
        'datastores': datastores,
        'queues': queues,
        'auth': auth,
        'external': external,
        'deployment': deployment,
        'tests': tests,
        'models': models,
        'migrations': migrations,
        'jobs': jobs,
        'compose': compose,
    }


def _hotspots(tree: SourceTree, services: list[dict], routes: list[dict], architecture: dict) -> list[dict]:
    if not services:
        return []
    hits: list[dict] = []

    def add(kind: str, severity: str, confidence: str, evidence: list[dict],
            recommendation: str, control: str) -> None:
        title, detail = HOTSPOT_COPY[kind]
        hits.append({'id': kind, 'title': title, 'detail': detail, 'severity': severity,
                     'confidence': confidence, 'evidence': evidence[:3],
                     'recommendation': recommendation, 'control': control})

    def scan(pattern: str, suffixes: set[str], max_hits: int = 3) -> list[dict]:
        found = []
        for relative in _backend_files(tree, services, suffixes):
            text = tree.text(relative)
            if not text:
                continue
            for match in re.finditer(pattern, text, re.M):
                found.append({'file': relative, 'line': _line(text, match.start()),
                              'snippet': _snippet(text, match.start())})
                if len(found) >= max_hits:
                    return found
        return found

    if architecture['datastores']:
        loop_query = scan(r'^\s*(?:for\s+[^:]+:|for\s*\(|\.map\s*\(\s*async|\.forEach\s*\(\s*async)'
                          r'[\s\S]{0,600}?(?:\.query\s*\(|\.filter\s*\(|\.findMany\s*\(|'
                          r'\.findAll\s*\(|\.objects\.|\.where\s*\(|SELECT\s+)',
                          {'.py', '.js', '.jsx', '.ts', '.tsx', '.rb'})
        if loop_query:
            add('n_plus_one', 'high', 'medium', loop_query,
                'Move the query outside the loop or batch the identifiers into one query.', 'db_pool')

    blocking = scan(r'async\s+def\s+[^\n]+[\s\S]{0,800}?(?:requests\.(?:get|post)|time\.sleep\(|open\()',
                    {'.py'})
    blocking += scan(r'(?:app|router)\.(?:get|post|put|patch|delete)\s*\([^\n]+[\s\S]{0,500}?'
                     r'(?:readFileSync|writeFileSync|execSync)', {'.js', '.ts'})
    if blocking:
        add('blocking_io', 'high', 'medium', blocking,
            'Use async I/O or move blocking work off the request path.', 'offload_jobs')

    external = architecture['external']
    if external and not architecture['queues']:
        add('missing_queue', 'medium', 'medium',
            [{'file': external[0]['evidence'][0], 'line': 1,
              'snippet': f"{external[0]['name']} dependency detected"}],
            'Consider a queue for retries and slow provider calls.', 'offload_jobs')
        add('sync_external', 'medium', 'low',
            [{'file': external[0]['evidence'][0], 'line': 1,
              'snippet': f"{external[0]['name']} is called from the service"}],
            'Check whether the call sits on a user-facing request path.', 'retry_policy')

    list_routes = [route for route in routes if route['method'] in ('GET', 'ANY')]
    if architecture['datastores'] and len(list_routes) >= 2:
        unbounded = scan(r'(?:findMany\s*\(|findAll\s*\(|\.objects\.all\s*\(\)|'
                         r'SELECT\s+\*)[\s\S]{0,180}?(?:;|\n)',
                         {'.py', '.js', '.jsx', '.ts', '.tsx', '.rb'}, max_hits=2)
        if unbounded and not any('limit' in item['snippet'].lower()
                                 or 'take' in item['snippet'].lower() for item in unbounded):
            add('unbounded_list', 'medium', 'low', unbounded,
                'Add an explicit page size and cursor or offset.', 'rate_limit')

    read_routes = [route for route in routes if route['method'] in ('GET', 'ANY')]
    if (architecture['datastores'] and len(read_routes) >= 4
            and not any(item['role'] == 'cache' for item in architecture['datastores'])):
        add('missing_cache', 'medium', 'low',
            [{'file': read_routes[0]['file'], 'line': read_routes[0]['line'],
              'snippet': f"{len(read_routes)} read routes detected"}],
            'Measure read latency before adding a cache; start with the hottest route.', 'cache_ttl_s')

    if architecture['models'] and not architecture['migrations']:
        model = architecture['models'][0]
        add('no_migrations', 'medium', 'medium',
            [{'file': model['file'], 'line': model['line'],
              'snippet': f"{model['framework']} model {model['name']}"}],
            'Add a migration path before changing the schema.', 'db_pool')

    if len(routes) >= 3 and not _has_route(routes, 'health'):
        add('no_health', 'low', 'medium',
            [{'file': routes[0]['file'], 'line': routes[0]['line'],
              'snippet': f"{len(routes)} routes and no health path"}],
            'Expose a small health/readiness endpoint.', 'replicas')

    if architecture['tests']['file_count'] == 0 and len(tree.files) > 12:
        add('no_tests', 'medium', 'medium',
            [{'file': services[0]['evidence'][0], 'line': 1,
              'snippet': 'No test files were detected'}],
            'Add a smoke and integration test before an architectural change.', 'replicas')

    mutation_routes = [route for route in routes
                       if route['method'] in ('POST', 'PUT', 'PATCH', 'DELETE')]
    if mutation_routes and not architecture['auth']:
        add('no_auth', 'medium', 'low',
            [{'file': mutation_routes[0]['file'], 'line': mutation_routes[0]['line'],
              'snippet': f"{mutation_routes[0]['method']} {mutation_routes[0]['path']}"}],
            'Confirm mutating routes are intentionally public or add authentication.', 'rate_limit')

    if architecture['datastores']:
        pool_hits = scan(r'(?:pool_size|max_connections|connectionLimit|maxPoolSize|'
                         r'minPoolSize|pool\s*[:=])', {'.py', '.js', '.ts', '.yml', '.yaml',
                                                       '.toml', '.properties'}, max_hits=1)
        if not pool_hits:
            add('no_pool', 'low', 'low',
                [{'file': architecture['datastores'][0]['evidence'][0], 'line': 1,
                  'snippet': f"{architecture['datastores'][0]['name']} dependency"}],
                'Make the connection pool explicit and bounded.', 'db_pool')

    return hits[:8]


def _readme_summary(tree: SourceTree) -> str:
    candidates = [relative for relative in tree.files if Path(relative).name.lower() == 'readme.md']
    if not candidates:
        return ''
    text = tree.text(sorted(candidates, key=len)[0])
    if not text:
        return ''
    text = re.sub(r'<!--[\s\S]*?-->', ' ', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'^\s*#+\s*', '', text, flags=re.M)
    text = re.sub(r'^\s*>\s?', '', text, flags=re.M)
    text = re.sub(r'(\*\*|__)(.*?)\1', r'\2', text)
    text = re.sub(r'(\*|_)(?=\S)(.*?)(?<=\S)\1', r'\2', text)
    text = text.replace('`', '')
    paragraphs = [re.sub(r'\s+', ' ', item).strip() for item in re.split(r'\n\s*\n', text)]
    for paragraph in paragraphs:
        if len(paragraph) >= 40 and not paragraph.lower().startswith(
                ('table of contents', 'installation', 'license', 'contributing')):
            return paragraph[:360]
    return ''


def _project_note(tree: SourceTree, project_type: str, services: list[dict],
                  architecture: dict, frontend: bool, primary_language: str) -> dict:
    readme = _readme_summary(tree)
    if services:
        what = readme or (
            f"{Path(tree.root).name} is a {primary_language or 'software'} project with "
            f"{len(services)} detected service(s)."
        )
        backend_names = ', '.join(
            f"{service['name']} ({service['framework']}, {service['language']})"
            for service in services[:3]
        )
        data = ', '.join(item['name'] for item in architecture['datastores']) or 'no database'
        queue = ', '.join(item['name'] for item in architecture['queues']) or 'no queue'
        backend = (
            f"The backend is {backend_names}. It uses {data} and {queue}. "
            f"{len(architecture['auth'])} authentication signal(s) and "
            f"{len(architecture['external'])} third-party integration(s) were detected."
        )
        request = (
            f"Requests enter through {'a gateway' if architecture['gateway'] else 'the service entry point'}, "
            f"then read or write data. {architecture['tests']['file_count']} test file(s) "
            f"and {len(architecture['deployment'])} deployment signal(s) are present."
        )
    elif frontend:
        what = readme or (
            f"{Path(tree.root).name} is a client-side application written in "
            f"{primary_language or 'web technology'}."
        )
        backend = (
            'No deployed server backend was found. The visible application runs in the browser '
            'or an app shell; any persistence is browser-local or supplied by an external service.'
        )
        request = 'The client handles its own state and calls external APIs only where a dependency proves it.'
    else:
        what = readme or f"{Path(tree.root).name} is a source repository."
        backend = 'No backend request path was detected from the inspected files.'
        request = 'DARWIN can summarise the source, but it cannot model a backend that is not present.'

    if services:
        evolution = (
            'The screening model can vary replicas, cache TTL, background offloading, retry policy, '
            'connection pool size, read replicas and rate limiting. It does not rewrite application code.'
        )
    else:
        evolution = (
            'Architecture screening is unavailable because no server request path was detected. '
            'A measured adapter may still be available for a narrow, audited code path.'
        )
    return {'what_it_is': what, 'backend': backend, 'how_it_works': request,
            'evolution': evolution, 'readme_used': bool(readme)}


def _screening_support(tree: SourceTree, services: list[dict], architecture: dict,
                       routes: list[dict]) -> dict:
    if not services:
        return {
            'available': False,
            'reason': 'No backend service or request path was detected, so there is no architecture to screen.',
            'controls': [],
        }
    controls = ['replicas']
    if any(item['role'] == 'cache' for item in architecture['datastores']) or len(routes) >= 2:
        controls.append('cache_ttl_s')
    if architecture['queues'] or architecture['jobs'] or architecture['external']:
        controls.append('offload_jobs')
    if architecture['external']:
        controls.append('retry_policy')
    if architecture['datastores']:
        controls.extend(['db_pool', 'read_replicas'])
    if len(routes) >= 2:
        controls.append('rate_limit')
    return {
        'available': True,
        'adapter_id': 'architecture-screening-v1',
        'adapter_version': '1.0.0',
        'display_name': 'Backend architecture evolution (simulated)',
        'evaluation_type': 'architecture_screening',
        'summary': (
            'Build a deterministic model from the inspected service, then compare architecture '
            'configurations. Repository code is never executed.'
        ),
        'change_summary': (
            'The baseline is the architecture detected in source. The candidate changes only '
            'deployment-level controls (replicas, cache, queue offload, retry, pool, read replica, rate limit).'
        ),
        'mechanism': (
            'A discrete-event queueing model uses the detected services, routes, data stores and '
            'integrations. It is uncalibrated and reports relative modelled differences, not measured runtime.'
        ),
        'scope_note': (
            'This is a screening recommendation, not a measured winner. No repository code, package '
            'manager, container or service is started. The model must be validated with a real deployment.'
        ),
        'correctness_rules': [
            'Every model input traces to an inspected file or an explicit assumption.',
            'The baseline and candidate use the same synthetic workload and seeds.',
            'A recommendation is only a candidate if the modelled error rate stays within policy.',
            'The original repository is never edited, executed, committed or pushed.',
        ],
        'controls': controls,
        'modes': [
            {'id': 'quick', 'label': 'Quick screening', 'estimated_seconds': 8,
             'description': 'One seed and a bounded variant set.'},
            {'id': 'full', 'label': 'Full screening', 'estimated_seconds': 20,
             'description': 'Three seeds and the full applicable control space.'},
        ],
        'execution_note': 'Simulation only. No repository code is executed.',
        'evidence': services[0]['evidence'][:2],
    }


def analyse_repository(root: str | Path, repository_url: str = '',
                        owner: str = '', repo: str = '') -> dict:
    """Return a deterministic, file-backed architecture profile for a checkout."""
    root = Path(root).resolve()
    tree = SourceTree.scan(root)
    manifests = [relative for relative in tree.files if Path(relative).name in MANIFESTS]
    dependencies = _all_dependencies(tree, manifests)
    languages = _count_languages(tree)
    primary_language = languages[0]['language'] if languages else ''
    frontend, frontend_evidence = _frontend_detected(tree, dependencies)
    services = _service_candidates(tree, dependencies)
    for service in services:
        service['framework'] = _pick_primary_framework(service, dependencies)
        service['route_count'] = 0
    routes = []
    for service in services:
        hits = _route_hits(tree, service['path'], service['language'])
        service['route_count'] = len(hits)
        routes.extend(hits)
    routes = routes[:400]
    architecture = _detect_architecture(tree, services, dependencies, routes, frontend,
                                        frontend_evidence)
    hotspots = _hotspots(tree, services, routes, architecture)
    screening = _screening_support(tree, services, architecture, routes)

    if services:
        project_type = 'multi_service_backend' if len(services) > 1 else \
            'node_service' if any(service['language'] == 'JavaScript/TypeScript' for service in services) else \
            'python_service' if any(service['language'] == 'Python' for service in services) else \
            'backend_service'
        display = ('Multi-service backend' if len(services) > 1 else
                   f"{services[0]['framework']} service")
        host = 'Container / process host'
        persistence = ', '.join(item['name'] for item in architecture['datastores']) or \
            'No database dependency detected'
        is_backend = True
        summary = (f"{display} with {len(routes)} detected route(s), "
                   f"{len(architecture['datastores'])} data store(s) and "
                   f"{len(architecture['queues'])} queue(s).")
    elif frontend:
        project_type = 'client_web_app'
        display = 'Client-side web application'
        host = 'Browser'
        persistence = 'Browser-local or external (no server backend detected)'
        is_backend = False
        summary = 'A browser application with no verified server entry point.'
    elif any(Path(relative).name in ('package.json', 'pyproject.toml', 'Cargo.toml',
                                     'go.mod', 'pom.xml', 'Gemfile', 'composer.json')
             for relative in tree.files):
        project_type = 'library'
        display = 'Library or package'
        host = 'Not an application'
        persistence = 'Not applicable'
        is_backend = False
        summary = 'A source package without a detected application entry point.'
    else:
        project_type = 'unknown_repository'
        display = 'Repository inspected'
        host = 'Not classified from source'
        persistence = 'Not classified from source'
        is_backend = False
        summary = 'DARWIN inspected the source but did not find a supported application shape.'

    note = _project_note(tree, project_type, services, architecture, frontend, primary_language)
    backend_profile = {
        'detected': bool(services),
        'services': services,
        'languages': languages[:6],
        'primary_language': primary_language,
        'frontend_detected': frontend,
        'frontend_evidence': frontend_evidence,
        'routes': routes,
        'route_count': len(routes),
        'datastores': architecture['datastores'],
        'queues': architecture['queues'],
        'auth': architecture['auth'],
        'external_services': architecture['external'],
        'deployment': architecture['deployment'],
        'tests': architecture['tests'],
        'models': architecture['models'][:20],
        'model_count': len(architecture['models']),
        'migrations': architecture['migrations'],
        'background_jobs': architecture['jobs'],
        'gateway': architecture['gateway'],
        'confidence': 'high' if services and (routes or architecture['datastores']) else
                      'medium' if services else 'low',
        'evidence': sorted({item for service in services for item in service.get('evidence', [])})[:8],
    }

    facts = []
    if languages:
        facts.append({'label': 'Languages', 'value': ', '.join(
            f"{item['language']} ({item['files']})" for item in languages[:4]),
            'evidence': [item['evidence'] for item in languages[:4]]})
    if frontend:
        facts.append({'label': 'Client application', 'value': 'Frontend dependency or component files detected',
                      'evidence': frontend_evidence})
    for service in services[:4]:
        facts.append({'label': 'Service', 'value': f"{service['name']} · {service['framework']} · {service['language']}",
                      'evidence': service['evidence'][:2]})
        if service['entry_points']:
            facts.append({'label': 'Entry point', 'value': service['entry_points'][0],
                          'evidence': service['entry_points'][:2]})
    for store in architecture['datastores'][:4]:
        facts.append({'label': 'Data store', 'value': store['name'],
                      'evidence': store['evidence'][:2]})
    for queue in architecture['queues'][:3]:
        facts.append({'label': 'Queue', 'value': queue['name'], 'evidence': queue['evidence'][:2]})
    if routes:
        facts.append({'label': 'HTTP routes', 'value': f"{len(routes)} detected",
                      'evidence': [routes[0]['file']]})
    if architecture['tests']['file_count']:
        facts.append({'label': 'Tests', 'value': f"{architecture['tests']['file_count']} test file(s)",
                      'evidence': architecture['tests']['evidence'][:2]})
    for item in architecture['deployment'][:3]:
        facts.append({'label': 'Deployment', 'value': item['name'], 'evidence': [item['evidence']]})

    not_supported = []
    if not services:
        not_supported.append({
            'capability': 'Backend architecture screening',
            'reason': 'No server service, route or data store was detected in the inspected source.',
        })
    if not architecture['datastores']:
        not_supported.append({
            'capability': 'Database tuning',
            'reason': 'No database dependency or connection string was found.',
        })
    if not architecture['queues']:
        not_supported.append({
            'capability': 'Queue tuning',
            'reason': 'No queue or worker dependency was found.',
        })
    if is_backend:
        not_supported.append({
            'capability': 'Measured runtime claims',
            'reason': 'Architecture screening is a model. DARWIN does not execute this repository.',
        })

    guesses = []
    if services and not routes:
        guesses.append({'label': 'HTTP surface', 'confidence': 'low',
                        'guess': 'A service entry point exists, but no route pattern was recognised.'})
    if any(store['name'] == 'SQL database' for store in architecture['datastores']):
        guesses.append({'label': 'Database engine', 'confidence': 'low',
                        'guess': 'An ORM was found, but the concrete engine was not visible.'})

    return {
        'project': {
            'type': project_type,
            'display_type': display,
            'summary': summary,
            'note': note,
            'application_host': host,
            'persistence': persistence,
            'is_server_backend': is_backend,
            'languages': [item['language'] for item in languages[:6]],
            'backend': backend_profile,
            'adapter_checks': {},
        },
        'architecture': {
            'nodes': architecture['nodes'],
            'edges': architecture['edges'],
            'flow': architecture['flow'],
            'summary': summary,
        },
        'facts': facts,
        'not_supported': not_supported,
        'hotspots': hotspots,
        'screening': screening,
        'guesses': guesses,
        'readiness': {
            'node_available': shutil.which('node') is not None,
            'node_version': None,
            'source_paths_present': bool(services),
            'adapter_approved': False,
            'source_tests_available': architecture['tests']['file_count'] > 0,
        },
    }
