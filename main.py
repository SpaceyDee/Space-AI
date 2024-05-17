import spacy
from nltk.corpus import cmudict
import nltk
import time

from database_utils import (
    get_user_input,
    preprocess_input,
    generate_response,
    print_response,
    handle_unknown_word,
    check_for_updates,
    connect_to_database,
    initialize_database,
    get_existing_words_from_database,
    get_new_words_from_json
)

nltk.download('cmudict')  # Ensure CMUDict is downloaded

# Load data and models
d = cmudict.dict()

DATA_DIR = "data/language"
nlp = spacy.load('en_core_web_sm')
new_words = []
last_update_time = time.time()

def main():
    connect_to_database()
    initialize_database("language_data.sql")

    word_data = {}  # Initialize word_data dictionary outside the loop

    while True:
        user_input = get_user_input(prompt="You: ")
        processed_input = preprocess_input(user_input)

        if processed_input.lower() == "exit":
            break

        # Update word_data with new or existing words
        new_words, all_word_data = get_new_words_from_json()
        existing_words = get_existing_words_from_database()
        word_data.update(all_word_data)

        # Generate response using updated word_data
        response = generate_response(processed_input, word_data)

        if response:
            print_response(response)
        else:
            handle_unknown_word(processed_input)

        check_for_updates() 

if __name__ == "__main__":
    main()