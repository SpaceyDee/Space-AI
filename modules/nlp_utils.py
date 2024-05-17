# In nlp_utils.py
import nltk  

def get_part_of_speech(word):
    text = nltk.word_tokenize(word)  # Tokenize into individual words
    tagged_words = nltk.pos_tag(text)  
    return tagged_words[0][1]  # Return the POS tag of the first (and only) word
