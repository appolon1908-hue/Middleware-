"""Real PostgreSQL concurrency proof for inclusive campaign ranges."""

import asyncio
import os
import uuid

import asyncpg


RUN_ID = "concurrency-" + uuid.uuid4().hex
SCHEMA_NAME = "campaign_concurrency_" + uuid.uuid4().hex
INSERT = """
INSERT INTO campaign_extension_allocation
(id,campaign_id,campaign_number,allocation_public_id,extension_start,
 extension_end,created_by,policy_hash,source_change_id)
VALUES($1,$2,$3,$4,$5,$6,'concurrency-test',$7,$8)
"""


async def insert(pool, name, number, start, end, delay=0):
    async with pool.acquire() as connection:
        transaction = connection.transaction()
        await transaction.start()
        try:
            await connection.execute(
                INSERT,
                uuid.uuid4(),
                f"{RUN_ID}-{name}",
                number,
                f"ALLOC-{RUN_ID}-{name}",
                start,
                end,
                "c" * 64,
                RUN_ID,
            )
            await asyncio.sleep(delay)
            await transaction.commit()
            return "PASS"
        except (
            asyncpg.DeadlockDetectedError,
            asyncpg.ExclusionViolationError,
        ):
            await transaction.rollback()
            return "OVERLAP"




async def create_isolated_pool(database_url):
    """Clone the migrated ledger so the proof cannot exhaust shared test data."""
    admin = await asyncpg.connect(database_url)
    try:
        await admin.execute(f"CREATE SCHEMA {SCHEMA_NAME}")
        await admin.execute(
            f"CREATE TABLE {SCHEMA_NAME}.campaign_extension_allocation "
            "(LIKE public.campaign_extension_allocation INCLUDING ALL)"
        )
    except Exception:
        await admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME} CASCADE")
        raise
    finally:
        await admin.close()

    return await asyncpg.create_pool(
        database_url,
        min_size=2,
        server_settings={"search_path": f"{SCHEMA_NAME},public"},
    )


async def drop_isolated_schema(database_url):
    admin = await asyncpg.connect(database_url)
    try:
        await admin.execute(f"DROP SCHEMA IF EXISTS {SCHEMA_NAME} CASCADE")
    finally:
        await admin.close()

async def main():
    database_url = os.environ["TEST_DATABASE_URL"]
    if "diag" not in database_url and "rehearsal" not in database_url:
        raise RuntimeError("concurrency proof requires an isolated test database")
    pool = await create_isolated_pool(database_url)
    extension_base, number_base = 6100, 100

    exact = await asyncio.gather(
        insert(pool, "EXACT1", number_base, extension_base, extension_base + 99, 0.1),
        insert(
            pool,
            "EXACT2",
            number_base + 100,
            extension_base,
            extension_base + 99,
        ),
    )
    assert sorted(exact) == ["OVERLAP", "PASS"]

    partial = await asyncio.gather(
        insert(
            pool,
            "PART1",
            number_base + 200,
            extension_base + 100,
            extension_base + 199,
            0.1,
        ),
        insert(
            pool,
            "PART2",
            number_base + 300,
            extension_base + 199,
            extension_base + 298,
        ),
    )
    assert sorted(partial) == ["OVERLAP", "PASS"]

    contained = await asyncio.gather(
        insert(
            pool,
            "OUTER",
            number_base + 400,
            extension_base + 300,
            extension_base + 399,
            0.1,
        ),
        insert(
            pool,
            "INNER",
            number_base + 500,
            extension_base + 320,
            extension_base + 330,
        ),
    )
    assert sorted(contained) == ["OVERLAP", "PASS"]

    adjacent = await asyncio.gather(
        insert(
            pool,
            "ADJ1",
            number_base + 600,
            extension_base + 400,
            extension_base + 499,
            0.1,
        ),
        insert(
            pool,
            "ADJ2",
            number_base + 700,
            extension_base + 500,
            extension_base + 599,
        ),
    )
    assert adjacent == ["PASS", "PASS"]

    many = await asyncio.gather(
        *[
            insert(
                pool,
                f"BLOCK{offset}",
                number_base + 800 + (offset * 100),
                extension_base + 600 + (offset * 10),
                extension_base + 609 + (offset * 10),
            )
            for offset in range(5)
        ]
    )
    assert many == ["PASS"] * 5

    async with pool.acquire() as connection:
        transaction = connection.transaction()
        await transaction.start()
        await connection.execute(
            INSERT,
            uuid.uuid4(),
            f"{RUN_ID}-ROLLBACK",
            number_base + 1300,
            f"ALLOC-{RUN_ID}-ROLLBACK",
            extension_base + 700,
            extension_base + 799,
            "c" * 64,
            RUN_ID,
        )
        await transaction.rollback()

    assert (
        await insert(
            pool,
            "AFTERROLLBACK",
            number_base + 1400,
            extension_base + 700,
            extension_base + 799,
        )
        == "PASS"
    )
    async with pool.acquire() as connection:
        await connection.execute(
            "UPDATE campaign_extension_allocation"
            " SET allocation_status='RETIRED' WHERE campaign_id=$1",
            f"{RUN_ID}-AFTERROLLBACK",
        )
    assert (
        await insert(
            pool,
            "REUSE",
            number_base + 1500,
            extension_base + 700,
            extension_base + 799,
        )
        == "OVERLAP"
    )
    async with pool.acquire() as connection:
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM campaign_extension_allocation"
                " WHERE source_change_id=$1",
                RUN_ID,
            )
            == 11
        )
    await pool.close()
    await drop_isolated_schema(database_url)
    print("CONCURRENT_OVERLAP_GATE=PASS")
    print("CONCURRENT_ADJACENT_GATE=PASS")
    print("RACE_CONDITION_GATE=PASS")
    print("TRANSACTION_ROLLBACK_GATE=PASS")
    print("RETIRED_RANGE_NON_REUSE_GATE=PASS")


if __name__ == "__main__":
    asyncio.run(main())
