import json
import os
import time
from pydoc import doc
import spacy
from database_utils import part_of_speech, ipa

from database_utils import (
  connect_to_database,
  get_definition_website1,
  get_definition_website2,
  get_ipa,
  get_new_words_from_json,
  insert_or_update_word,
  word_exists_in_database,
)

nlp = spacy.load("en_core_web_sm")
db_filename = "language_data.db"
start_time = time.time()
new_words, all_word_data = get_new_words_from_json()
cursor = None
conn = None

connect_to_database()


def add_new_words_to_database(new_words_filename="data/language/new_words.json", db_filename="language_data.db"):
  with open(new_words_filename, 'r') as f:
    new_words = json.load(f)

  with connect_to_database() as conn:
    cursor = conn.cursor()
    for word in new_words:
      data = all_word_data.get(word)
      insert_or_update_word(conn, data)

    conn.commit()


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
  cursor = conn.cursor()
  cursor.execute("SELECT pos FROM words WHERE word = ?", (word,))
  result = cursor.fetchone()

  if result:
    return result[0]
  else:
    doc = nlp(word)
    return doc[0].pos_


def create_database(data_dir, database_name="language_data.db"):

  connect_to_database()
  cursor = conn.cursor()

  for filename in os.listdir('data/language'):
    if filename.endswith(".json"):
      with open(os.path.join('data/language', filename), 'r') as f:
        data = json.load(f)
        for word, word_info in data.items():
          word = word_info['word']

          check_query = f"SELECT EXISTS(SELECT 1 FROM {part_of_speech} WHERE word=%s)"
          cursor.execute(check_query, (word,))

          if not cursor.fetchone()[0]:
            insert_query = f"INSERT INTO {part_of_speech} (word, lemma, ipa, definition) VALUES (%s, %s, %s, %s)"
            cursor.execute(insert_query, (word, word_info.get('lemma'), word_info.get('ipa'), word_info.get('definition')))
          else:
            definition = word_info.get('definition')
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

  for word_data in data.values():
    word = word_data['word']
    check_query = f"SELECT EXISTS(SELECT 1 FROM {language} WHERE word=?)"
    cursor.execute(check_query, (word,))
    if not cursor.fetchone()[0]:
      insert_query = f"INSERT INTO {part_of_speech} (word, lemma, ipa, definition) VALUES (?, ?, ?, ?)"
    cursor.execute(insert_query, (word, word_data.get('lemma'), word_data.get('ipa'), word_data.get('definition')))
  conn.commit()

  while True:
    for filename in os.listdir(data_dir):
      if filename.endswith(".json"):
        language = filename.split(".")[0]
        with open(os.path.join(data_dir, filename), 'r') as f:
          data = json.load(f)
        for word in data:
          check_query = f"SELECT EXISTS(SELECT 1 FROM {language} WHERE word=?)"
          cursor.execute(check_query, (word,))
          if not cursor.fetchone()[0]:
            insert_query = f"INSERT INTO {language} (word) VALUES (?)"
          cursor.execute(insert_query, (word,))

          word_data = data[word]
          if not word_data.get('definition'):
            definition = get_definition_website1(word_data['word'])
            if definition:
              word_data['definition'] = definition
            else:
              definition = get_definition_website2(word_data['word'])
              if definition:
                word_data['definition'] = definition

            if definition:
              with open(os.path.join(data_dir, filename), 'w') as f:
                json.dump(data, f, indent=4)
    conn.commit()


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
              insert_or_update_word(conn, {"word": word, "definition": word_info.get("definition")})


if __name__ == "__main__":
  create_tables()

  new_words, all_word_data = get_new_words_from_json()  # Call before database connection
  if new_words:
    add_new_words_to_database()  # Now with correct connection

  add_other_json_files()
