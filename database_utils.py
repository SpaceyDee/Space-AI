import spacy
import string
import os
import requests
from bs4 import BeautifulSoup
import json
import pyphen
import sqlite3
import lxml.html as lhtml

nlp = spacy.load('en_core_web_sm')
db_filename = "language_data.db"
DATABASE_NAME = 'language_data.sql'

conn = None
cursor = None

def connect_to_database():
    return sqlite3.connect(db_filename)

def create_tables():
  with connect_to_database() as conn:
    cursor = conn.cursor()
    cursor.executescript(
      '''
      CREATE TABLE IF NOT EXISTS words (
        word_id INTEGER PRIMARY KEY AUTOINCREMENT,
        word TEXT UNIQUE,
        lemma TEXT,
        ipa TEXT,
        pos TEXT,
        definition TEXT
      );

      CREATE TABLE IF NOT EXISTS parts_of_speech(
        pos_id INT AUTO_INCREMENT PRIMARY KEY,
        pos_type TEXT
      );

      CREATE TABLE IF NOT EXISTS word_pos(
        word_id INT,
        pos_id INT,
        PRIMARY KEY(word_id, pos_id),
        FOREIGN KEY(word_id) REFERENCES words(word_id),
        FOREIGN KEY(pos_id) REFERENCES parts_of_speech(pos_id)
      );

      CREATE TABLE IF NOT EXISTS synonyms(
        synonym_id INT AUTO_INCREMENT PRIMARY KEY,
        word_id INT,
        synonym_word_id INT,
        FOREIGN KEY(word_id) REFERENCES words(word_id),
        FOREIGN KEY(synonym_word_id) REFERENCES words(word_id)
      );

      CREATE TABLE IF NOT EXISTS definitions (
        definition_id INT AUTO_INCREMENT PRIMARY KEY,
        word_id INT,
        definition TEXT,
        example_usage TEXT,
        FOREIGN KEY(word_id) REFERENCES words(word_id)
      );

      CREATE TABLE IF NOT EXISTS antonyms (
        antonym_id INT AUTO_INCREMENT PRIMARY KEY,
        word_id INT,
        antonym_word_id INT,
        FOREIGN KEY(word_id) REFERENCES words(word_id),
        FOREIGN KEY(antonym_word_id) REFERENCES words(word_id)
      );

      CREATE TABLE IF NOT EXISTS word_families (
        family_id INT AUTO_INCREMENT PRIMARY KEY,
        root_word TEXT
      );

      CREATE TABLE IF NOT EXISTS word_family_members (
        word_id INT,
        family_id INT,
        PRIMARY KEY(word_id, family_id),
        FOREIGN KEY(word_id) REFERENCES words(word_id),
        FOREIGN KEY(family_id) REFERENCES word_families(family_id)
      );

      CREATE TABLE IF NOT EXISTS origins (
        origin_id INT AUTO_INCREMENT PRIMARY KEY,
        language TEXT
      );

      CREATE TABLE IF NOT EXISTS word_origins (
        word_id INT,
        origin_id INT,
        PRIMARY KEY(word_id, origin_id),
        FOREIGN KEY(word_id) REFERENCES words(word_id),
        FOREIGN KEY(origin_id) REFERENCES origins(origin_id)
      );
      '''
    )

  conn.commit()

def get_part_of_speech(conn, word):
    with conn.cursor() as cursor:
        cursor.execute("SELECT pos FROM words WHERE word = ?", (word,))
        result = cursor.fetchone()

    if result:
        return result[0]  # Return the POS directly
    else:
        doc = nlp(word)
        return doc[0].pos_  # Return the POS from spaCy

def get_new_words_from_json():
    new_words = set()
    all_word_data = {}
    for filename in os.listdir('data/language'):
        if filename.endswith(".json"):
            with open(os.path.join('data/language', filename), 'r') as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON in file {filename}: {e}")
                    continue
                # Handle both dictionary and list of dictionaries format
                if isinstance(data, list):
                    for word_dict in data:
                        all_word_data.update(word_dict)
                        new_words.update(word_dict.keys())
                else:
                    all_word_data.update(data)
                    new_words.update(data.keys())
                # Rest of the word processing (lemmatization etc.)
                for word in new_words:
                    doc = nlp(word)
                    token = doc[0]
                    word_data = {
                        "word": token.text,
                        "lemma": token.lemma_,
                        "pos": token.pos_,
                        "entity_type": token.ent_type_,
                    }
                    all_word_data[word] = word_data
    return new_words, all_word_data

def get_existing_words_from_database():
    existing_words = set()
    cursor.execute("SELECT word FROM words")
    results = cursor.fetchall()

    for result in results:
        existing_words.add(result[0])  

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

def generate_response(input_text, word_data):
    input_doc = nlp(input_text)

    most_similar_word = None
    highest_similarity = 0.0

    for word, info in word_data.items(): 
        word_doc = nlp(word)
        similarity = input_doc.similarity(word_doc)

        if similarity > highest_similarity:
            highest_similarity = similarity
            most_similar_word = word

    if most_similar_word:
        definition = word_data[most_similar_word].get("definition")
        return f"{most_similar_word}: {definition}"
    else:
        return None

def print_response(response):
    print("Bot:", response)

def write_new_words_to_json(words, filename="data/language/new_words.json"):
    with open(filename, 'w') as f:
        json.dump(list(words), f, indent=4)

def check_for_updates():
    new_words, all_word_data = get_new_words_from_json()
    existing_words = get_existing_words_from_database()

    words_to_insert = new_words - existing_words  

    for word in words_to_insert:
        word_data = all_word_data[word]  
        pos_tag = word_data.get("pos", "ADJECTIVE")  
        insert_word(word, word_data['lemma'], get_ipa(word), pos_tag)

    update_words_with_missing_info()

    conn.commit()


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
            insert_word(word, word.lemma_, ipa)  

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
    except (IOError, json.JSONDecodeError) as e:  
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

def word_exists_in_database(conn, word): 
    cursor = conn.cursor()
    cursor.execute("SELECT EXISTS(SELECT 1 FROM words WHERE word = ?)", (word,))
    result = cursor.fetchone()
    return bool(result[0])

def insert_word(word, lemma, ipa, pos="ADJECTIVE"):  
    connect_to_database()
    table_name = pos.lower() + "s" 

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS {} (
            word VARCHAR(255) PRIMARY KEY,
            lemma VARCHAR(255),
            ipa VARCHAR(255),
            definition TEXT
        )
    """.format(table_name))

    cursor.execute("""
        INSERT INTO {} (word, lemma, ipa, pos, definition) 
        VALUES (%s, %s, %s, %s, NULL)  -- Definition can be added later
    """.format(table_name), (word, lemma, ipa, pos))

    conn.commit()

def insert_or_update_word(conn, word_data):
    with conn.cursor() as cursor:
        word = word_data['word']
        part_of_speech = get_part_of_speech(conn, word) # Retrieve POS before using it
        table_name = part_of_speech.lower() + "s"

        cursor.execute(
            f"SELECT definition FROM {table_name} WHERE word = ?", (word,)
        )
        existing_definition = cursor.fetchone()

    if existing_definition and existing_definition[0] is not None:
        pass
    else:
        definition = word_data.get("definition")
        if not definition:
            definition = get_definition_website1(word) or get_definition_website2(word)

        if existing_definition:
            cursor.execute(
                f"UPDATE {table_name} SET definition = ? WHERE word = ?",
                (definition, word),
            )
        else:
            cursor.execute(
                f"""
                INSERT INTO {table_name} (word, lemma, ipa, definition)
                VALUES (?, ?, ?, ?)
                """,
                (word, word_data.get('lemma'), get_ipa(word), definition),
            )

def add_other_json_files():
    global all_word_data
    with connect_to_database() as conn:
        cursor = conn.cursor()

        for filename in os.listdir('data/language'):
            if filename.endswith(".json") and filename != "new_words.json":
                with open(os.path.join('data/language', filename), 'r') as f:
                    data = json.load(f)
                    for word, word_info in data.items():
                        if not word_exists_in_database(conn, word):
                            insert_or_update_word(
                                conn, {"word": word, "definition": word_info.get("definition")}
                            )

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

if __name__ == "__main__":
    create_tables()
    add_other_json_files()
