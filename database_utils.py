import json
import string
import aiosqlite
import requests
import spacy
import os
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import lxml.html as lhtml
import pyphen
from time import time

nlp = spacy.load("en_core_web_sm")
db_filename = "language_data.db"

async def create_connection_pool():
    return await aiosqlite.connect(db_filename)

conn = asyncio.run(create_connection_pool())
cursor = None

async def create_tables():
    async with conn.cursor() as cursor:
        await cursor.executescript('''
            CREATE TABLE IF NOT EXISTS words (
                word_id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT UNIQUE,
                lemma TEXT,
                ipa TEXT,
                pos TEXT,
                definition TEXT
            );

            -- create parts_of_speech table 
            CREATE TABLE IF NOT EXISTS parts_of_speech(
                pos_id INT PRIMARY KEY,
                pos_type TEXT
            );
        ''')
        parts_of_speech = ["Noun", "Pronoun", "Verb", "Adjective", "Adverb", "Preposition", "Conjunction", "Interjection"]
        for pos in parts_of_speech:
            await cursor.execute(
                "INSERT OR IGNORE INTO parts_of_speech (pos_type) VALUES (?)",
                (pos,),
            )

asyncio.run(create_tables())

async def get_part_of_speech(conn, word):
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT pos FROM words WHERE word = ?", (word,))
        result = await cursor.fetchone()

    if result:
        return result[0]
    else:
        doc = nlp(word)
        return doc[0].pos_

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


async def get_existing_words_from_database(conn):
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT word FROM words")
        results = await cursor.fetchall()
    return set(result[0] for result in results)

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

    conn.commit()

def insert_word(word, lemma, ipa, pos="ADJECTIVE"):  
    table_name = pos.lower() + "s"

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            word_id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT UNIQUE,
            lemma TEXT,
            ipa TEXT,
            definition TEXT
        )
    """)

    cursor.execute(
        f"""
        INSERT INTO {table_name} (word, lemma, ipa, definition)
        VALUES (?, ?, ?, NULL)  -- Definition can be added later
        """,
        (word, lemma, ipa),
    )

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

async def word_exists_in_database(conn, word):
    async with conn.execute("SELECT EXISTS(SELECT 1 FROM words WHERE word = ?)", (word,)) as cursor:
        result = await cursor.fetchone()
        return bool(result[0])


async def insert_word_async(conn, word_data):
    word = word_data['word']
    lemma = word_data.get('lemma', word)  # Default to the word itself if lemma is missing
    ipa = get_ipa(word) 
    pos = word_data['pos']  # Retrieve POS directly from word_data

    table_name = pos.lower() + "s"

    # Create table if it doesn't exist
    async with conn.cursor() as cursor:  # Use async context manager
        await cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                word_id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT UNIQUE,
                lemma TEXT,
                ipa TEXT,
                definition TEXT
            )
            """
        )

        # Insert word data into words table
        await cursor.execute(
            """
            INSERT INTO words (word, lemma, ipa, pos, definition)
            VALUES (?, ?, ?, ?, NULL)  -- Definition can be added later
            """,
            (word, lemma, ipa, pos),
        )

        # Check if the word is already in the specific part-of-speech table
        await cursor.execute(f"SELECT 1 FROM {table_name} WHERE word = ?", (word,))
        if not await cursor.fetchone():  # If the word doesn't exist, insert it
            await cursor.execute(
                f"""
                INSERT INTO {table_name} (word, lemma, ipa, definition) 
                VALUES (?, ?, ?, NULL)  
                """,
                (word, lemma, ipa),
            )

def word_exists_in_database(conn, word): 
    cursor = conn.cursor()
    cursor.execute("SELECT EXISTS(SELECT 1 FROM words WHERE word = ?)", (word,))
    result = cursor.fetchone()
    return bool(result[0])

def insert_or_update_word(conn, word_data):
    word = word_data['word']
    part_of_speech = get_part_of_speech(conn, word)
    table_name = part_of_speech.lower() + "s"

    cursor.execute(
        f"SELECT definition FROM words WHERE word = ?", (word,)
    )
    existing_definition = cursor.fetchone()

    if existing_definition and existing_definition[0] is not None:
        pass
    else:
        definition = word_data.get("definition")
        if not definition:
            definition = get_definition_website1(word) or get_definition_website2(word)

        cursor.execute("SELECT 1 FROM words WHERE word = ?", (word,))
        if cursor.fetchone():
            cursor.execute("UPDATE words SET definition = ? WHERE word = ?", (definition, word))
        else:
            cursor.execute(
                "INSERT INTO words (word, lemma, ipa, pos, definition) VALUES (?, ?, ?, ?, ?)",
                (word, word_data.get('lemma'), get_ipa(word), part_of_speech, definition),
            )
    conn.commit()  

async def fetch_definition(session, word, url_func):
    try:
        async with session.get(url_func(word)) as response:
            if response.status == 200:
                content = await response.text()
                if "urbandictionary" in url_func(word):
                    return get_definition_website1(word, content)  
                else:
                    return get_definition_website2(word, content)
            else:
                return None
    except aiohttp.ClientError as e:
        print(f"Error fetching definition for '{word}': {e}")
        return None

async def get_definitions_concurrently(words):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for word in words:
            task1 = asyncio.create_task(fetch_definition(session, word, get_definition_website1))
            task2 = asyncio.create_task(fetch_definition(session, word, get_definition_website2))
            tasks.extend([task1, task2])
        results = await asyncio.gather(*tasks)
        definitions = {}
        for word, (def1, def2) in zip(words, results):
            definitions[word] = def1 or def2  #
        return definitions

async def process_file(filename, all_word_data):
    tasks = []
    with open(os.path.join('data/language', filename), 'r') as f:
        data = json.load(f)
        for word, word_info in data.items():
            if not await word_exists_in_database(conn, word):
                word_data = {
                    "word": word,
                    "definition": word_info.get("definition")
                }
                if word_data["definition"] is None:
                    insert_or_update_word_async.append(word)  
                else:
                    tasks.append(
                        asyncio.create_task(insert_or_update_word_async(conn, word_data))
                    )
    await asyncio.gather(*tasks)

def add_new_words_to_database(all_word_data):
    start_time = time()
    filename = "data/language/new_words.json"
    with open(filename, 'r') as f:
        new_words = json.load(f)

    for word in new_words:
        data = all_word_data.get(word)
        insert_or_update_word(conn, data)
        print(f"Added/updated word: {word}")

    end_time = time()
    print(f"Finished adding new words in {end_time - start_time:.2f} seconds")

async def add_other_json_files(all_word_data):
    tasks = []
    words_to_insert = []
    batch_size = 1000
    for filename in os.listdir('data/language'):
        if filename.endswith(".json") and filename != "new_words.json":
            tasks.append(
                asyncio.create_task(process_file(filename, all_word_data, conn, words_to_insert)) 
            )

    await asyncio.gather(*tasks)  

    if words_to_insert:
        definitions = await get_definitions_concurrently(words_to_insert)
        async with conn.execute("begin"):  
            for word, definition in definitions.items():
                if definition:  
                    await conn.execute(
                        "UPDATE words SET definition = ? WHERE word = ?",
                        (definition, word),
                    )
            await conn.commit()

async def insert_or_update_word_async(conn, word_data):
    word = word_data['word']
    part_of_speech = await get_part_of_speech(conn, word)
    table_name = part_of_speech.lower() + "s"

    async with conn.cursor() as cursor:
        await cursor.execute(
            f"SELECT definition FROM words WHERE word = ?", (word,)
        )
        existing_definition = await cursor.fetchone()

        if existing_definition and existing_definition[0] is not None:
            pass
        else:
            definition = word_data.get("definition")

            await cursor.execute("SELECT 1 FROM words WHERE word = ?", (word,))
            if await cursor.fetchone():  
                await cursor.execute("UPDATE words SET definition = ? WHERE word = ?", (definition, word))
            else:  
                await cursor.execute(
                    "INSERT INTO words (word, lemma, ipa, pos, definition) VALUES (?, ?, ?, ?, ?)",
                    (word, word_data.get('lemma'), get_ipa(word), part_of_speech, definition),
                )

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

async def word_exists_in_database(conn, word):
    async with conn.execute("SELECT EXISTS(SELECT 1 FROM words WHERE word = ?)", (word,)) as cursor:
        result = await cursor.fetchone()
        return bool(result[0])