import os
from darwin.contracts import Genome


def genome():
    return Genome.model_validate_json(os.environ.get('DARWIN_GENOME_JSON', '{}'))
