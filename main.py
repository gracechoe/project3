import json
import re
import math
import sys
from bs4 import BeautifulSoup
from pymongo import MongoClient
from collections import defaultdict
from nltk.stem.snowball import SnowballStemmer
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

"""
Notes: 
- example of an entry in index_col:
    {'token': "foo", 'documents': ['3/34', '5/36'], 'word_freq': [1,2], 'tf-idf': [0.02, 0.005]}
- example of an entry in doc_col:
    {'doc':'3/34', 'terms_count':71}
- index_col.create_index({'token':1}) <-- key command to making program run faster
"""
# MAKE SURE TO CHANGE to respective directory! 
path = "/Users/gracechoe/Documents/WEBPAGES_RAW/"
bookkeeping = open(path+"bookkeeping.json", "r")
data = json.load(bookkeeping)
client = MongoClient("mongodb://localhost:27017/")
db = client["INVERTED_INDEX"]
index_col = db["index"]
doc_col = db["docs"]
stemmer = SnowballStemmer("english")

# initialize() goes through each key in bookkeeping.json and calls process_file on it.
def initialize():
    global path
    count = 0

    for key in data:
        count += 1
        print(count) 
        # if count == 500:
        #     process_file(key)
        #     break
        process_file(key)

"""
(1) Takes in a string path that points to where the desired file is contained
(2) Reads the file and uses BeautifulSoup to parse the html of the file for tokens
(3) Note: tokens_count can't be more than 10000 and the leng(token) can't be more than 20
"""
def process_file(key):
    global path
    global index_col
    global doc_col
    global stemmer

    # read the file
    f = open(path+key)
    soup = BeautifulSoup(f.read(), "html.parser")

    try:
        soup.prettify()
        text = find_tags(soup)
        tokens = re.findall(r"[A-Za-z0-9]+", text.lower()) #find tokens in the file

        # create temp dictionary to hold tokens as keys and token frequency as value
        # ex. freq_dict = {"token1": 3, "token2":5, "token3": 6}
        token_count = 0 
        freq_dict = {}

        for token in tokens:
            token = stemmer.stem(token)
            if token_count > 30000:
                raise Exception('Token dict too long')
            if len(token) < 20:
                token_count += 1
                if token in freq_dict:
                    freq_dict[token] += 1
                else:
                    freq_dict[token] = 1

        update_collections(freq_dict, key, token_count)
        
    except:
        print("caught an error")
        pass

# retrieves all text of the file after extracting parts of the file under certain tags 
def find_tags(soup):
    [s.extract() for s in soup(['style', 'script', 'head'])]
    result = soup.get_text()
    return result

""" 
(1) Current document and specific token frequency info is added to the respective token entry
(2) index_col and doc_col are both updated with new info
"""
def update_collections(freq_dict, key, terms_count):
    global index_col
    global doc_col

    for token, freq in freq_dict.items(): 
        if index_col.find_one({'token': token}): # if this token exists in index_col
            query = {'token': token}
            new_values = {"$push": {'documents': key, 'word_freq': freq}}
            index_col.update_one(query, new_values) # update with additional doc and freq
        else:
            entry = {'token': token, 'documents': [key], 'word_freq': [freq], 'tf-idf': []}
            result = index_col.insert(entry) # create new token entry in index_col

    entry = {'doc':key, 'terms_count':terms_count} # add new entry in doc_col
    doc_col.insert(entry)

# calculates and updates the tf-idf value for each token in the database
def complete_index():
    global index_col
    global doc_col
    doc_count = doc_col.count()
    print(doc_count)
    entry_count = 0

    for entry in index_col.find().batch_size(50):
        entry_count += 1
        print(entry_count)

        docs = entry['documents']
        freqs = entry['word_freq']
        token = entry['token']

        for doc, freq in zip(docs, freqs):
            result = doc_col.find_one({'doc': doc})
            try: 
                term_count = result['terms_count']
                tf = float(freq) / term_count 
                idf = math.log(float(doc_count)/len(docs))
                tf_idf = tf*idf

                index_col.update_one({'token':token},{"$push":{'tf-idf':tf_idf}})
            except:
                print("caught an error")
                pass

# retrieves all urls that contain the token, returns a string with 20 of those urls and total url count
@app.route("/get_urls/<tokens>")
def get_urls(tokens):
    global data
    result = []
    count = 0
    tokens = re.findall(r"[A-Za-z0-9]+", tokens.decode('utf-8').lower())

    query_dict = compute_queries(tokens)
    ranked = sorted(query_dict.items(), key=lambda k: (-k[1][1], -k[1][0]))
    
    for doc, _ in ranked:
        if count < 20:
            result.append(data[doc])
        count += 1
    return jsonify(result)

# creates a dictionary of documents with the respective td-idf and token count
def compute_queries(tokens):
    global index_col
    global stemmer
    d = defaultdict(list)
    for token in tokens:
        entry = index_col.find_one({'token':stemmer.stem(token)})
        if entry:
            for doc, tf_idf in zip(entry["documents"], entry["tf-idf"]):
                if doc in d:
                    d[doc][0] += tf_idf
                    d[doc][1] += 1
                else:
                    d[doc] = [tf_idf, 1]
    return d

if __name__ == "__main__":
    initialize()
    complete_index()
    app.run(host='0.0.0.0')