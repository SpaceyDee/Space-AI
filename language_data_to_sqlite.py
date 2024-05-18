import asyncio
import time
import cProfile
from database_utils import (
    get_new_words_from_json,
    insert_or_update_word_async,  
    add_other_json_files,
    get_existing_words_from_database,
    create_connection_pool,
    create_tables,
)
db_filename = "language_data.db"
conn = asyncio.run(create_connection_pool())

async def main():
    start_time = time.time()
    new_words, all_word_data = get_new_words_from_json()
    existing_words = await get_existing_words_from_database(conn)
    words_to_insert = new_words - existing_words

    print(f"Loaded {len(new_words)} new words from JSON in {time.time() - start_time:.2f} seconds")
    if words_to_insert:
        tasks = []
        for word in words_to_insert:
            data = all_word_data.get(word)
            tasks.append(asyncio.create_task(insert_or_update_word_async(conn, data)))

        await asyncio.gather(*tasks)  
        conn.commit()


    await add_other_json_files(all_word_data)
    print("All done! Database populated successfully.")

    end_time = time.time()
    print(f"Total time: {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(create_tables())

    cProfile.run("asyncio.run(main())", sort="tottime")
