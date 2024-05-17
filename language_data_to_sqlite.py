import json
import os
import time
from pydoc import doc
import spacy

from database_utils import (
  connect_to_database,
  get_definition_website1,
  get_definition_website2,
  get_new_words_from_json,
  word_exists_in_database,
  create_tables,
  get_ipa,
  insert_or_update_word
)

nlp = spacy.load("en_core_web_sm")
db_filename = "language_data.db"
start_time = time.time()
new_words, all_word_data = get_new_words_from_json()
cursor = None
conn = None

connect_to_database()

def part_of_speech(conn, word):
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
                cursor.execute(update_query, (doc[0].lemma_, get_ipa, word))
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

def get_part_of_speech(conn, word):
    with conn.cursor() as cursor:  # Use a with block for better resource management
        cursor.execute("SELECT pos FROM words WHERE word = ?", (word,))
        result = cursor.fetchone()

        if result:
            return result[0]
        else:
            doc = nlp(word)
            return doc[0].pos_




def add_new_words_to_database(new_words_filename="data/language/new_words.json", db_filename="language_data.db"):
  with open(new_words_filename, 'r') as f:
    new_words = json.load(f)

  with connect_to_database() as conn:
    cursor = conn.cursor()
    for word in new_words:
      data = all_word_data.get(word)
      insert_or_update_word(conn, data)

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

  new_words, all_word_data = get_new_words_from_json() 
  if new_words:
    add_new_words_to_database()
  else:
    print("No new words to add to database.") 
    
    add_other_json_files()
    print("All words added to database.")
    print(f"Total time: {time.time() - start_time} seconds")
else:
  print("This file is not meant to be imported.")
