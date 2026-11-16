# Backend — ASP.NET Core Web API

Implements the specification in `docs/API_SPECIFICATION.md`. Waves 1 and 2 of the §10.2 order are done: **9 endpoints**.

| Section | Endpoint | |
|---|---|---|
| 7.1.1 | `POST /auth/register` | 🌐 |
| 7.1.2 | `POST /auth/login` | 🌐 |
| 7.1.3 | `POST /auth/refresh` | 🌐 |
| 7.1.4 | `GET /auth/me` | 🔒 |
| 7.2.1 | `GET /profile` | 🔒 |
| 7.2.2 | `PUT /profile` | 🔒 |
| 7.2.3 | `GET /profile/nutrition-targets` | 🔒 |
| 7.2.4 | `GET /profile/conditions` | 🔒 |
| 7.2.5 | `PUT /profile/conditions` | 🔒 |

34 public endpoints and 4 internal ones are still to be built — see `docs/API_SPECIFICATION.md` §6.

---

## Running it

```bash
python tools/run_backend.py            # http://localhost:5000/api/v1
```

That file feeds `.env` into the `dotnet` process, and generates a `JWT_SIGNING_KEY` into `.env` if there is none.

**There is no default signing key in the source, deliberately.** This repository is public; a key sitting in a committed file means anyone who can read the repository can sign a valid token for any account. The server **stops at startup** when the key is missing or shorter than 32 characters, rather than running with an empty one — running with an empty key looks perfectly normal until somebody tries it.

It needs a running MySQL with the `nutrition_rec` database built from `db/schema.sql`.

---

## Three layers of checks, and why all three are needed

```
python tools/check_be_parity.py     Step 1: C# <-> Dart <-> Python   76 checks
python tools/smoke_backend.py       9 endpoints on real MySQL        93 checks
python tools/gen_entities.py        C# entities + ENUMs <-> db/schema.sql
```

The three layers catch three different classes of bug, and none of them substitutes for another.

**`check_be_parity.py` — the arithmetic.** Step 1 is implemented **three times**: `Api/Nutrition/NutritionTargets.cs`, `mobile/lib/data/models/health_profile.dart`, and the reference implementation in `tools/gen_step1_cases.py`. The three run in three layers and never meet, so when they drift nothing reports it: the app shows one energy target, the server generates a plan from a different one, and both numbers look plausible.

This suite caught three real divergences on its very first run — a 17/60/23 macro split in Dart against the 15/60/25 in the database and the specification; `mealDistribution` 25/40/27/8 in the specification against the midpoints 27.5/37.5/27.5/7.5 in `meal_plan.dart`; and `bmiCategory: "normal"` for a BMI of 23.15, wrong by the very Asian thresholds 23/25 the system uses. None of the three looks wrong when you read it.

`tools/test_be_parity.py` is a negative test of that suite itself: it injects 14 errors into the case file and demands that both suites fail. It only modifies the **generated** file and never touches source — an earlier version edited the constants in `NutritionTargets.cs` directly and restored them in a `finally`, and when the session was cut off halfway the `finally` never ran: the injected error stayed behind in the real code.

**`smoke_backend.py` — what only breaks once there is a database and a network.** Column name mapping, data types, transactions, the error envelope, the claims in a JWT. It creates an account with a random email and deletes it at the end; `ON DELETE CASCADE` clears the rest.

It has caught four bugs the compiler could not see: `food_tags` missing its primary key (declared at table level, and without it **every** endpoint returns 500, not only the ones touching that table); `CHAR(36)` reading back as `System.Guid` instead of `string`; the self-referential `replaced_by` foreign key breaking because EF put the `UPDATE` before the `INSERT`; and a check inside the test file itself hard-coding a date of birth, so its result changed on exactly one day of the year.

**`gen_entities.py` — 24 entity classes generated from `db/schema.sql`.** 225 columns; typed by hand, one wrong column name or wrong `NULL`-ability causes no compile error at all — it causes a `MySqlException` at run time, at an endpoint nobody might call for weeks. Run with no flag it **audits** the existing code; with `--write` it regenerates.

Its check 5 compares four arrays in `Api/Profile/ProfileDtos.cs` — `Enums.Gender`, `.ActivityLevel`, `.Goal`, `.Severity` — against the ENUM value sets of `health_profiles` and `user_conditions`, **order included**, because MySQL stores an ENUM by ordinal. Those four arrays are the only layer returning `400 VALIDATION_FAILED` with a field name, so when they drift from the schema the API rejects exactly what the database permits, and both sides stay self-consistent so nothing reports it. The check runs **both ways**: adding an array to `Enums` without declaring it in `ENUM_CS` is drift too — it looks audited while in fact it is not.

---

## Four decisions that affect everything afterwards

### One single time zone: Asia/Ho_Chi_Minh

`Api/Time/Clock.cs` is the only place that reads a clock. Every `DATETIME` column takes `Clock.Now`; every `DATE` column and every calendar-day calculation takes `Clock.Today`.

Before that, three layers read three clocks: the database used `CURRENT_TIMESTAMP` on 27 columns and `NOW()` in every `tools/*.py`, both returning `@@session.time_zone` which defaults to `SYSTEM`, that is Vietnam time; the Flutter app used `DateTime.now()`, local time; and the backend used `DateTime.UtcNow`, **7 hours off from both**. The consequences were silent: a `users.created_at` written by the backend was 7 hours behind a row written by `check_ml_e2e.py`, so sorting by `created_at` mixed two clocks. And "today" computed in UTC was a **day** behind between 00:00 and 07:00, so on their actual birthday the app showed 23 while `GET /profile` returned `age: 22`.

Vietnam time rather than UTC, because that is what the database **already** stores — switching to UTC would mean changing the schema's 27 defaults, every `NOW()` in `tools/`, and the data already written.

**One exception, and it is mandatory:** a JWT's `nbf`/`exp` are seconds since the Unix epoch and so are always UTC (RFC 7519 §2). `TokenService.CreateAccessToken` is the only place left using `DateTime.UtcNow`. Putting Vietnam time there would place `nbf` 7 hours in the future, and with `ClockSkew = TimeSpan.Zero` **every** token would be rejected the moment it was issued.

### Blocking a disabled account with a global filter, not a check at each site

`ActiveAccountFilter` is registered in `MvcOptions.Filters`, so a new endpoint is protected **by default**; removing the protection has to be explicit, with `[AllowAnonymous]`. Before that, `is_active` was checked at `/auth/login`, `/auth/refresh` and `/auth/me` but **not** at any `/profile` endpoint, so a disabled account could still read and write its profile for up to an hour. 38 endpoints are still to be built, and a check that has to be remembered at every site is a check that will be forgotten.

`/auth/login` and `/auth/refresh` keep their own check, and that is not duplication: they are `[AllowAnonymous]` and authenticate with a password or a refreshToken, so there is no `sub` claim for the filter to look up.

### No EF Core Migrations

`db/migrations/applied/README.md` states it plainly: **`db/schema.sql` is the schema's current state.** Enabling Migrations would create a second source of authority for the same schema, and the two would drift — `tools/check_schema_sql.py` catches that, but only *after* the drift.

Changing the schema follows exactly three steps:

```bash
# 1. write db/migrations/00N_name.sql, then run
python tools/run_sql.py db/migrations/00N_name.sql --database nutrition_rec
# 2. fold it into db/schema.sql and update the counts at the top of the file
# 3. regenerate the entities
python tools/gen_entities.py --write
```

Adding a table reaches four more documents — `DATABASE_DESIGN.md`, `database_erd.html`, `ERD_REVIEW.md`, and the expected count in `tools/test_schema_build.py`. `python tools/check_docs_sync.py` lists each place exactly.

### `GuidFormat=None` in the connection string

The schema has 45 `CHAR(36)` columns, and all 45 are UUIDs. MySqlConnector defaults to `GuidFormat=Char36`, so it returns a `System.Guid` for every `CHAR(36)` column — while the entities declare `string`, and EF throws `InvalidCastException` on the first **read**. `Program.cs` normalises the connection string to force `GuidFormat=None`, including a string the user supplies through `MYSQL_CONNECTION`.

The entities stay `string` rather than becoming `Guid`, because specification §2.3 states the primary keys are "36-character UUID strings" and every query in the system — `tools/*.py` and `ml/*.py` included — compares them as strings.

---

## Layout

```
Api/
├── Program.cs              JWT, the §2.5 error envelope, the connection
│                           string, the global filter
├── Data/AppDbContext.cs    24 tables        <- GENERATED
├── Entities/               24 classes       <- GENERATED
├── Http/
│   ├── ApiError.cs         the error envelope + the 21-code catalogue of §4
│   └── ActiveAccount.cs    blocks a disabled account at EVERY endpoint
├── Time/Clock.cs           one single time zone: Asia/Ho_Chi_Minh
├── Nutrition/              Step 1: BMI, BMR, TDEE, macros, meal split
├── Auth/                   7.1.1 – 7.1.4
└── Profile/                7.2.1 – 7.2.5
Api.Tests/                  44 checks, no database needed
```

The two directories marked **GENERATED** are not edited by hand — change `db/schema.sql` and run `tools/gen_entities.py --write` again.
