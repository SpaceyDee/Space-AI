import spacy
import string
import os
import requests
from bs4 import BeautifulSoup
import json
import pyphen
import lxml.html as lhtml
import mysql.connector

nlp = spacy.load('en_core_web_sm')
DATABASE_NAME = 'language_data.sql'

# Create a global database connection and cursor
conn = None
cursor = None

def initialize_database(database_file):
    print(f"Initializing database from file: {database_file}") 
    if not os.path.exists(database_file):
        print(f"Database file not found at: {database_file}") 
        try:
            with open(database_file, "r") as f:
                sql = f.read()
            conn = mysql.connector.connect(
                # Your MySQL credentials
                host="127.0.0.1",
                user="root", 
                password="StavenKoning13"
            )
            cursor = conn.cursor()
            cursor.execute(sql, multi=True)  # Allows multiple statements in the SQL file 
            conn.commit()
        except Exception as e:
            print(f"Error initializing database: {e}")

def get_new_words_from_json():
    new_words = set()  # Use a set for simple comparisons
    all_word_data = {}
    for filename in os.listdir('data/language'):
        if filename.endswith(".json"):
            with open(os.path.join('data/language', filename), 'r') as f:
                data = json.load(f)
                for word, word_info in data.items():
                    if word not in new_words:
                        new_words.add(word)  # Add words to the set
                        all_word_data[word] = word_info
                        doc = nlp(word)
                        token = doc[0]
                        word_data = {
                            "word": token.text,
                            "lemma": token.lemma_,
                            "pos": token.pos_,
                            "entity_type": token.ent_type_,
                        }
                        all_word_data[word] = word_data  # Store word data in the dictionary
    return new_words, all_word_data

def get_existing_words_from_database():
    existing_words = set()
    cursor.execute("SELECT word FROM words")
    results = cursor.fetchall()

    for result in results:
        existing_words.add(result[0])  # Extract word from result

    return existing_words

def tokenize_text(text):
    doc = nlp(text)
    tokens = [token.text for token in doc]
    return tokens

def process_word(word):
    doc = nlp(word)
    token = doc[0]
    return {
        "word": token.text,
        "lemma": token.lemma_,
        "pos": token.pos_,
        "entity_type": token.ent_type_,
    }

def get_user_input(prompt):
    while True:
        try:
            response = input(prompt)
            if response:
                return response
            else:
                print("Please enter a valid response.")
        except ValueError:
            print("Invalid input. Please try again.")

def generate_response(input, mind_data):
    doc = nlp(input)

    most_similar_word = None
    highest_similarity = 0.0
    for word in mind_data:
        token = nlp(word)
        similarity = doc.similarity(token)
        if similarity > highest_similarity:
            highest_similarity = similarity
            most_similar_word = word

    return most_similar_word

def print_response(response):
    print("Bot:", response)

def write_new_words_to_json(words, filename="data/language/new_words.json"):
    with open(filename, 'w') as f:
        json.dump(list(words), f, indent=4)

def check_for_updates():
    new_words, all_word_data = get_new_words_from_json()
    existing_words = get_existing_words_from_database()

    words_to_insert = new_words - existing_words  # Find words not in the database

    for word in words_to_insert:
        word_data = all_word_data[word]  
        pos_tag = word_data.get("pos", "ADJECTIVE")  # Get POS or default to "ADJECTIVE"
        insert_word(word, word_data['lemma'], get_ipa(word), pos_tag)

    update_words_with_missing_info()

def update_words_with_missing_info():
    """Fetches definitions and IPA for words that lack them in the database."""
    cursor.execute("SELECT word FROM words WHERE definition IS NULL OR ipa IS NULL") 
    words_to_update = cursor.fetchall()

    for word_tuple in words_to_update:
        word = word_tuple[0]

        # Try getting definition
        definition, example = get_definition_website1(word)
        if not definition:
            definition = get_definition_website2(word)

        if definition:
            add_definition(word, definition)

        # Get IPA if needed
        if not get_ipa(word):  
            ipa = get_ipa(word)
            insert_word(word, word.lemma_, ipa)  # Update the IPA in the database

def word_exists_in_database(word):
    """Efficiently checks if a word exists in the database."""
    cursor.execute("SELECT EXISTS(SELECT 1 FROM words WHERE word = %s)", (word,))
    result = cursor.fetchone()

    return bool(result[0])

def handle_unknown_word(word):
    definition = get_user_input("I'm not familiar with the word '{}'. Could you please define it for me? ".format(word))
    ipa = get_ipa(word)
    new_word_data = {
        "word": word,
        "definition": definition,
        "lemma": word,
        "ipa": ipa
    }
    doc = nlp(word)
    lemma = doc[0].lemma_

    try:
        with open('data/language/new_words.json', 'r') as f:
            new_words = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading new words file: {e}")
        new_words = {}

    new_words[word] = new_word_data

    try:
        with open('data/language/new_words.json', 'w') as f:
            json.dump(new_words, f, indent=4)
    except (IOError, json.JSONDecodeError) as e:  # IOError covers more potential file issues
        print(f"Error saving new words file: {e}")

    insert_word(word, lemma, ipa)
    check_for_updates()
    print(f"'{word}' added to the database.")

def handle_user_input(user_input):
    processed_input = preprocess_input(user_input)
    response = generate_response(processed_input)

    if response is None:
        handle_unknown_word(processed_input)
        return

    print_response(response)

def preprocess_input(user_input):
    punctuation = string.punctuation
    translator = str.maketrans('', '', punctuation)
    clean_input = user_input.lower().title()
    return clean_input.translate(translator)

def get_ipa(word):
    try:
        hyphenated = pyphen.Pyphen(lang='en')
        return hyphenated.inserted(word)
    except Exception as e:
        print(f"IPA retrieval error for '{word}': {e}")
        return None

def connect_to_database():  # Remove the database_name argument
    global conn, cursor
    if conn is None or not conn.is_connected():
        conn = mysql.connector.connect(
            host="127.0.0.1",
            user="root",
            password="StavenKoning13"
        )
        cursor = conn.cursor()

def insert_word(word, lemma, ipa, pos="ADJECTIVE"):  # Default to 'ADJECTIVE' 
    connect_to_database()
    table_name = pos.lower() + "s"  # e.g., "adjectives", "nouns", etc.

    # Create the table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS {} (
            word VARCHAR(255) PRIMARY KEY,
            lemma VARCHAR(255),
            ipa VARCHAR(255),
            definition TEXT
        )
    """.format(table_name))

    # Insert into the appropriate table 
    cursor.execute("""
        INSERT INTO {} (word, lemma, ipa, pos, definition) 
        VALUES (%s, %s, %s, %s, NULL)  -- Definition can be added later
    """.format(table_name), (word, lemma, ipa, pos))

    conn.commit()

def get_definition_website1(word):
    try:
        url = f"https://www.urbandictionary.com/define.php?term={word}"
        response = requests.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        try:
            definition_div = soup.find('div', attrs={'class': 'meaning'})
            if definition_div:
                definition = definition_div.text.strip()
            else:
                definition = None

            example_div = soup.find('div', attrs={'class': 'example'})
            if example_div:
                example = example_div.text.strip()
            else:
                example = None

            return definition, example

        except AttributeError:
            return None, None

    except requests.exceptions.RequestException as e:
        print(f"Error occurred while making the request: {str(e)}")
        return None, None

def get_definition_website2(word):
    url = f"https://www.oed.com/search/dictionary/?scope=Entries&q={word}"
    response = requests.get(url)
    response.raise_for_status()

    try:
        html_tree = lhtml.fromstring(response.content)
        first_definition = html_tree.xpath("//div[@class='resultsSetItem'][1]//div[@class='snippet']/text()")[0].strip()
        return first_definition

    except (IndexError, AttributeError):
        return None

def add_definition(word, definition):
    connect_to_database()

    cursor.execute("""
        UPDATE adjectives SET definition = %s
        WHERE word = %s
    """, (definition, word))

    conn.commit()

# Connect to the database
connect_to_database()
initialize_database("language_data.sql") 
