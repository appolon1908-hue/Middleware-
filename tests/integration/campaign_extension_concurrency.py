"""Real PostgreSQL concurrency proof for inclusive campaign ranges."""

import asyncio
import os
import uuid

import asyncpg


RUN_ID = "concurrency-" + uuid.uuid4().hex
INSERT = """
INSERT INTO {table}
(id,campaign_id,campaign_number,allocation_public_id,extension_start,
 extension_end,created_by,policy_hash,source_change_id)
VALUES($1,$2,$3,$4,$5,$6,'concurrency-test',$7,$8)
"""


async def insert(pool, table, name, number, start, end, delay=0):
    async with pool.acquire() as connection:
        transaction = connection.transaction()
        await transaction.start()
        try:
            await connection.execute(
                INSERT.format(table=table),
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


async def create_scratch_schema(database_url: str) -> str:
    connection = await asyncpg.connect(database_url)
    schema = "concurrency_" + uuid.uuid4().hex
    try:
        await connection.execute(f'CREATE SCHEMA "{schema}"')
        await connection.execute(
            f'CREATE TABLE "{schema}".campaign_extension_allocation '
            "(LIKE public.campaign_extension_allocation INCLUDING ALL)"
        )
    finally:
        await connection.close()
    return schema


async def drop_scratch_schema(database_url: str, schema: str) -> None:
    connection = await asyncpg.connect(database_url)
    try:
        await connection.execute(f'DROP SCHEMA "{schema}" CASCADE')
    finally:
        await connection.close()



async def find_test_bases(pool, table):
    """Choose a free extension band and unique campaign numbers for this run."""
    async with pool.acquire() as connection:
        extension_base = None
        for candidate in range(6100, 9201, 100):
            occupied = await connection.fetchval(
                f"""
                SELECT EXISTS (
                    SELECT 1
                    FROM {table}
                    WHERE extension_range && int4range($1, $2, '[]')
                )
                """,
                candidate,
                candidate + 799,
            )
            if not occupied:
                extension_base = candidate
                break
        if extension_base is None:
            raise RuntimeError("no free extension range available for concurrency test")
        max_number = await connection.fetchval(
            "SELECT COALESCE(MAX(campaign_number), 0) "
            f"FROM {table}"
        )
    number_base = ((int(max_number) // 100) + 1) * 100
    return extension_base, number_base

async def main():
    database_url = os.environ["TEST_DATABASE_URL"]
    assert "diag" in database_url or "rehearsal" in database_url
    schema = await create_scratch_schema(database_url)
    table = f'"{schema}".campaign_extension_allocation'

    async def configure_connection(connection):
        await connection.execute(f'SET search_path TO "{schema}", public')

    pool = await asyncpg.create_pool(database_url, init=configure_connection)
    try:
        extension_base, number_base = await find_test_bases(pool, table)

        exact = await asyncio.gather(
            insert(pool, table, "EXACT1", number_base, extension_base, extension_base + 99, 0.1),
            insert(
                pool,
                table,
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
                table,
                "PART1",
                number_base + 200,
                extension_base + 100,
                extension_base + 199,
                0.1,
            ),
            insert(
                pool,
                table,
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
                table,
                "OUTER",
                number_base + 400,
                extension_base + 300,
                extension_base + 399,
                0.1,
            ),
            insert(
                pool,
                table,
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
                table,
                "ADJ1",
                number_base + 600,
                extension_base + 400,
                extension_base + 499,
                0.1,
            ),
            insert(
                pool,
                table,
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
                    table,
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
                INSERT.format(table=table),
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
                table,
                "AFTERROLLBACK",
                number_base + 1400,
                extension_base + 700,
                extension_base + 799,
            )
            == "PASS"
        )
        async with pool.acquire() as connection:
            await connection.execute(
                f"UPDATE {table}"
                " SET allocation_status='RETIRED' WHERE campaign_id=$1",
                f"{RUN_ID}-AFTERROLLBACK",
            )
        assert (
            await insert(
                pool,
                table,
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
                    f"SELECT count(*) FROM {table}"
                    " WHERE source_change_id=$1",
                    RUN_ID,
                )
                == 11
            )
        print("CONCURRENT_OVERLAP_GATE=PASS")
        print("CONCURRENT_ADJACENT_GATE=PASS")
        print("RACE_CONDITION_GATE=PASS")
        print("TRANSACTION_ROLLBACK_GATE=PASS")
        print("RETIRED_RANGE_NON_REUSE_GATE=PASS")
    finally:
        await pool.close()
        await drop_scratch_schema(database_url, schema)


if __name__ == "__main__":
    asyncio.run(main())
