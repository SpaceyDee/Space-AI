import json
from pydoc import doc
import time
import spacy
import os
import mysql.connector
from database_utils import (
    get_new_words_from_json,
    get_definition_website1, 
    get_definition_website2
)

nlp = spacy.load("en_core_web_sm")
db_filename = "language_data.db" 
start_time = time.time()
new_words, all_word_data = get_new_words_from_json()
cursor = None
conn = None


# Database connection and creation
def get_part_of_speech(word):
    from database_utils import connect_to_database
    connect_to_database()

    cursor.execute("SELECT pos FROM words WHERE word = %s", (word,))  
    result = cursor.fetchone()

    if result:
        return result[-1]  # Return POS from the database
    else:
        doc = nlp(word)
        token = doc[-1]
        part_of_speech = token.pos_

        # Update the database with the new POS 
        cursor.execute("""
            UPDATE words 
            SET pos = %s
            WHERE word = %s
        """, (part_of_speech, word))

        conn.commit()

        return part_of_speech
    
def create_database(data_dir, database_name="language_data.db"):
  from database_utils import part_of_speech, ipa
  conn = mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password="StavenKoning13",
        database=database_name
  )
  cursor = conn.cursor()

  for filename in os.listdir('data/language'):
    if filename.endswith(".json"):
      with open(os.path.join('data/language', filename), 'r') as f:
        data = json.load(f)  
        for word, word_info in data.items():
          word = word_data['word'] 
 
          check_query = f"SELECT EXISTS(SELECT 1 FROM {part_of_speech} WHERE word=%s)"
          cursor.execute(check_query, (word,))
          
          if not cursor.fetchone()[0]: 
            insert_query = f"INSERT INTO {part_of_speech} (word, lemma, ipa, definition) VALUES (%s, %s, %s, %s)"
            cursor.execute(insert_query, (word, word_data.get('lemma'), word_data.get('ipa'), word_data.get('definition')))
          else:
            definition = word_data.get('definition')
          if not definition: 
            definition = get_definition_website1(word) or get_definition_website2(word)
            if definition:
              update_query = f"""
              UPDATE {part_of_speech} 
              SET lemma = %s, ipa = %s
              WHERE word = %s AND (lemma IS NULL OR ipa IS NULL)
            """
            cursor.execute(update_query, (doc[0].lemma_, ipa, word))
            conn.commit()
  conn.close()

  create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {part_of_speech} (
      word TEXT PRIMARY KEY,
      lemma TEXT, 
      ipa TEXT,
      definition TEXT  
    );
  """
  cursor.execute(create_table_query)

  for word_data in data.values():  # Iterate over word_data objects
    word = word_data['word']  # Extract the word
    check_query = f"SELECT EXISTS(SELECT 1 FROM {language} WHERE word=?)"
    cursor.execute(check_query, (word,))
    if not cursor.fetchone()[0]:  # If the word doesn't exist
      insert_query = f"INSERT INTO {part_of_speech} (word, lemma, ipa, definition) VALUES (?, ?, ?, ?)"
    cursor.execute(insert_query, (word, word_data.get('lemma'), word_data.get('ipa'), word_data.get('definition')))
  conn.commit()

  # Insert data from JSON files into their respective tables
  while True:
    for filename in os.listdir(data_dir):
      if filename.endswith(".json"):
        language = filename.split(".")[0]
        with open(os.path.join(data_dir, filename), 'r') as f:
          data = json.load(f)
        for word in data:
          check_query = f"SELECT EXISTS(SELECT 1 FROM {language} WHERE word=?)"
          cursor.execute(check_query, (word,))
          if not cursor.fetchone()[0]:  # If the word doesn't exist
            insert_query = f"INSERT INTO {language} (word) VALUES (?)"
          cursor.execute(insert_query, (word,))

          # Check if definition is missing
          word_data = data[word]
          if not word_data.get('definition'):
            # Attempt Website 1
            definition = get_definition_website1(word_data['word'])
            if definition:
              word_data['definition'] = definition
            else:
              # Attempt Website 2
              definition = get_definition_website2(word_data['word'])
              if definition:
                word_data['definition'] = definition

            # Update the JSON file if a definition was found
            if definition:  
              with open(os.path.join(data_dir, filename), 'w') as f:
                json.dump(data, f, indent=4)
    conn.commit()

def create_tables():
  conn = mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password="StavenKoning13",
        database="language_data"
  )
  cursor = conn.cursor()

  cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS words(
      word_id INT AUTO_INCREMENT PRIMARY KEY,
      word TEXT UNIQUE,
      lemma TEXT,
      ipa TEXT,
      definition TEXT
    )
  ''')

  cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS parts_of_speech(
      pos_id INT AUTO_INCREMENT PRIMARY KEY, 
      pos_type TEXT 
    )
  ''')

  cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS word_pos(
      word_id INT,
      pos_id INT,
      PRIMARY KEY(word_id, pos_id), 
      FOREIGN KEY(word_id) REFERENCES words(word_id),
      FOREIGN KEY(pos_id) REFERENCES parts_of_speech(pos_id)
    )
  ''')

  cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS synonyms(
      synonym_id INT AUTO_INCREMENT PRIMARY KEY,
      word_id INT, 
      synonym_word_id INT, 
      FOREIGN KEY(word_id) REFERENCES words(word_id),
      FOREIGN KEY(synonym_word_id) REFERENCES words(word_id) 
    )
  ''')

  cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS definitions (
      definition_id INT AUTO_INCREMENT PRIMARY KEY,
      word_id INT,  
      definition TEXT,
      example_usage TEXT, 
      FOREIGN KEY(word_id) REFERENCES words(word_id)
    )
  ''')

  cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS antonyms (
      antonym_id INT AUTO_INCREMENT PRIMARY KEY,
      word_id INT, 
      antonym_word_id INT, 
      FOREIGN KEY(word_id) REFERENCES words(word_id),
      FOREIGN KEY(antonym_word_id) REFERENCES words(word_id) 
    )
  ''')

  cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS word_families (
      family_id INT AUTO_INCREMENT PRIMARY KEY,
      root_word TEXT
    )
  ''')

  cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS word_family_members (
      word_id INT,
      family_id INT,
      PRIMARY KEY(word_id, family_id),
      FOREIGN KEY(word_id) REFERENCES words(word_id),
      FOREIGN KEY(family_id) REFERENCES word_families(family_id)
    )
  ''')

  cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS origins (
      origin_id INT AUTO_INCREMENT PRIMARY KEY,
      language TEXT 
    )
  ''')

  cursor.execute(''' 
    CREATE TABLE IF NOT EXISTS word_origins (
      word_id INT,
      origin_id INT,
      PRIMARY KEY(word_id, origin_id),
      FOREIGN KEY(word_id) REFERENCES words(word_id),
      FOREIGN KEY(origin_id) REFERENCES origins(origin_id)
    )
  ''')

  conn.commit()
  conn.close()

if new_words:
  def add_new_words_to_database(new_words_filename="data/language/new_words.json", db_filename="language_data.db"):
    with open(new_words_filename, 'r') as f:
      new_words = json.load(f)

    conn = mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password="StavenKoning13",
        database="language_data"
    )
    cursor = conn.cursor()
    for word in new_words:
      data = all_word_data.get(word)  # Retrieve associated data
      cursor.execute("INSERT INTO words (word, lemma, ipa, definition) VALUES (%s, %s, %s, %s)",
                     (word, data.get('lemma'), data.get('ipa'), data.get('definition')))
    conn.commit()
    conn.close()

  add_new_words_to_database()

