import requests
from urllib.parse import urlparse
from x_client_transaction.utils import handle_x_migration, get_ondemand_file_url, generate_headers
from x_client_transaction import ClientTransaction
import bs4
import re

import re

def get_url_path(url):
    path = re.findall(r'https?://x\.com(.*?)\?', url)[0]
    return path

def get_transaction_id():
    # https://github.com/iSarabjitDhiman/XClientTransaction
    
    session = requests.Session()
    session.headers = generate_headers()
    response = handle_x_migration(session)
    ondemand_file_url = get_ondemand_file_url(response)
    ondemand_file = session.get(url=ondemand_file_url)
    ondemand_file_response = bs4.BeautifulSoup(ondemand_file.content, 'html.parser')
    ct = ClientTransaction(response,ondemand_file_response)
    return ct