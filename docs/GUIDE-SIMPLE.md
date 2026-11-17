# DARWIN in plain terms

Every term gets two things: a simple definition, then an everyday example. Nothing else.

## The app

**DARWIN**
Means: An architecture experiment lab for a small online shop. You build a version, run it under traffic, break it on purpose, check it never charges twice, and only then compare speed, cost and recovery.
Example: A racing test bench. You build an engine, run it under load, break it on purpose, and check it does not cheat the safety rules before you compare lap times.

**Baseline**
Means: The plain, working shop that every test is compared against.
Example: The original recipe before you start changing ingredients. It is not claimed to be the best; it is the starting point.

**Candidate**
Means: A shop with changed settings that you are testing against the baseline.
Example: The new recipe version you want to compare with the original.

## The lab (home page)

**The lab**
Means: The home screen. It states the decision, the six-step method, what is real today, and whether the test bench is ready.
Example: The dashboard at the entrance of a lab: the question being settled, the method on the wall, the equipment that actually exists, and whether it is plugged in.

**Illustrative decision**
Means: A worked example of the product's judgement. Basic is cheap but slow, Cached is the balance, Distributed is fastest but fails the duplicate-payment rule, so it is rejected.
Example: Three cars on a track. The fastest one fails the safety check and does not win. The cost figures shown (₹10,000 / ₹20,000 / ₹35,000) are hypothetical examples, not DARWIN results.

**Six-step method**
Means: Understand the backend → generate alternatives → run experiments under traffic → introduce failures → verify business correctness → search the trade-offs.
Example: A recipe contest: read the recipe, write variants, cook them, burn one on purpose, taste-test for safety, then rank only the ones that are actually edible.

**Why not just AWS, Kubernetes and load tests?**
Means: Those tools supply servers, containers, traffic and numbers. DARWIN coordinates the decision: which architecture should carry the next 10,000 users, and which candidates must be rejected even if they are fast.
Example: A workshop has a lathe, a welder and a paint booth. None of them decides which chair design to ship.

## Test & break page

**Quick checkout smoke**
Means: A short test that starts the shop and checks it can take an order, then take the exact same order again without creating a second one.
Example: Opening a new till, selling one coffee, then scanning the same receipt again. It should say "already paid", not charge twice.

**Normal baseline vs candidate**
Means: Run the plain shop and an improved shop under normal traffic, then compare their numbers.
Example: Two coffee stalls, one with a single cashier and one with two cashiers plus a menu board. Give both the same queue and see who serves faster.

**Experiment type**
Means: The kind of test you are running: speed only, speed plus breaking things, a deliberate payment failure, or just switching it on.
Example: A car can be tested for lap time, crash safety, or simply whether the key turns.

**Configuration**
Means: The four settings that describe the shop.
Example: Four dials on a washing machine: temperature, spin speed, run time, extra rinse. Change the dials, change the wash.

**Runtime (Native vs Docker)**
Means: Where the shop runs. Native means normal programs on this laptop. Docker means the same shop sealed inside containers.
Example: Cooking in your own kitchen versus cooking in a rented food truck. Same recipe, different setup time and cleanup.

**Workload**
Means: The kind of customer traffic the test sends.
Example: A normal day is a few customers. A flash sale is a four-second stampede. Checkout heavy is a queue where almost everyone buys.

**p95**
Means: 95 out of 100 requests were faster than this number; the slowest 5 were slower.
Example: 100 people order. 95 get their receipt in under 300 ms and 5 wait longer. p95 is 300 ms.

**CPU s**
Means: How many seconds of actual thinking the app did during the test.
Example: In a 12-second test the app used 2.4 seconds of CPU, like a worker who was busy 20% of the shift.

**Recovery s**
Means: How long after a fault is removed until the shop is healthy again.
Example: Unplug the database for two seconds, plug it back in, and the shop is normal three seconds later. Recovery is 3 s.

## Evolve page

**Evolve (search)**
Means: The computer tries many shop settings, tests the promising ones for real, and keeps the best trade-offs.
Example: Trying 36 recipes, tasting a few, and keeping the fastest and the cheapest. The untasted recipes are never called winners.

**NSGA-II**
Means: A smart trying method that mixes good settings and keeps several good-but-different options.
Example: A chef combining two good recipes and keeping both the quick version and the cheap version.

**Hill climbing**
Means: Start with the normal shop, change one setting at a time, and keep the change if it helps.
Example: Tuning a bike. Raise the seat one notch, pedal; if it feels better, keep going; stop when nothing feels better.

**Random search**
Means: Try settings at random, to see whether the smart method actually beat guessing.
Example: Picking lottery numbers randomly instead of using a system. It shows whether the system is worth anything.

**Measured attempts**
Means: How many real test runs the search is allowed to do. Each setting costs three runs.
Example: You have six exam attempts and each subject needs three. You can only sit two subjects for real.

**Seed**
Means: A number that makes the random test repeatable.
Example: A shuffled deck with the shuffle written down. Same number, same shuffle; different number, different shuffle.

**Screened**
Means: A setting the computer guessed might be good, but has not tested for real.
Example: A job applicant who passed the CV check but has not been interviewed.

**Promoted**
Means: A setting chosen for a real test, and that test is running now.
Example: The applicant is in the interview room right now.

**Measured feasible**
Means: Tested for real three times and passed every rule.
Example: Passed the interview, the background check, and the trial shift.

**Measured rejected**
Means: Tested for real and broke a rule, so it is out even if it was fast.
Example: The fastest runner, disqualified for cheating.

**Measured incomplete**
Means: A real test started but did not finish, so there is no full result.
Example: The interview was cut off halfway. You cannot hire or reject based on it.

**Recovery unavailable**
Means: The test passed on speed, but one number needed to rank it is missing.
Example: A race where the finish-line camera failed. Fast-looking, but no official time.

**Pareto front**
Means: The options where nothing else is better on everything. You choose based on what you care about.
Example: One car is fast but thirsty; one is slow but cheap. Both are real choices, and neither is simply "best".

**No feasible candidate**
Means: None of the tested settings passed all the rules.
Example: Every applicant failed the background check. The honest answer is "nobody yet", not "pick the least bad".

## Alternatives page

**API replicas**
Means: How many copies of the checkout counter are running.
Example: One cashier versus three cashiers. Three serve more people but cost more wages.

**Catalog cache (0 / 10 / 30 s)**
Means: A short memory of the product list so the shop does not ask the database every time. Stock is still checked live.
Example: Writing the menu on a board for 10 seconds. You do not reprint it for every customer, but you still check whether a dish is sold out.

**Notifications (sync vs queued)**
Means: Either send the "order confirmed" message immediately, or put it in a queue for a helper to send.
Example: Telling the customer "your coffee is ready" yourself, versus writing it on a slip for the runner.

**Retries (none vs idempotent)**
Means: Whether to try a failed step once more, and only safely, using the same order number.
Example: The card machine beeps but prints nothing. Try again with the same receipt number, never with a fresh charge.

**Service connections**
Means: The lines showing which parts talk to which.
Example: A restaurant floor plan: waiter to kitchen to till. More waiters means more lines to the kitchen.

**Configuration hash**
Means: A short fingerprint of the four settings.
Example: A locker number. The same settings get the same locker; change one thing and you get a different locker.

**Simulated performance**
Means: A quick computer estimate of speed before doing the real test.
Example: A weather forecast. Useful for planning, but you still look outside.

## Demo shop

**Demo shop**
Means: A tiny shop used to show that resending an order never creates a second order or a second charge.
Example: 20 notebooks. Order one with receipt K: 19 left, one charge. Resend K five times: still 19, still one charge, same receipt. Same ticket, same coat.

## The whole app in one sentence

A fast shop that charges twice is worse than a slow shop that charges once — so DARWIN breaks each design, verifies the business rules, and only then ranks the survivors on speed, cost and recovery.