import asyncio
import time
import spacy
import cProfile
from database_utils import (
    connect_to_database,
    get_new_words_from_json,
    add_new_words_to_database,
    add_other_json_files,
    create_tables,
)

nlp = spacy.load("en_core_web_sm")
db_filename = "language_data.db"

def main():
    start_time = time.time()
    new_words, all_word_data = get_new_words_from_json()
    end_time = time.time()
    print(f"Loaded {len(new_words)} new words from JSON in {end_time - start_time:.2f} seconds")

    if new_words:
        add_new_words_to_database(all_word_data)

    asyncio.run(add_other_json_files(all_word_data)) 
    
if __name__ == "__main__":
    create_tables()
    
    connect_to_database()
    
    cProfile.run("main()")