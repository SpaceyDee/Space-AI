import asyncio
import time
import cProfile
from database_utils import (
    get_new_words_from_json,
    add_new_words_to_database,
    add_other_json_files,
    create_tables,
)
def main():
    start_time = time()
    new_words, all_word_data = get_new_words_from_json()
    end_time = time()
    print(f"Loaded {len(new_words)} new words from JSON in {end_time - start_time:.2f} seconds")

    if new_words:
        add_new_words_to_database(all_word_data)

    asyncio.run(add_other_json_files(all_word_data))
    print("All done! Database populated successfully.")
    print(f"Total time: {time.time() - start_time} seconds")

if __name__ == "__main__":
    create_tables()
    cProfile.run("main()")