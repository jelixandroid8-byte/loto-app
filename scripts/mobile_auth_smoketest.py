import requests

import os

BASE = os.environ.get('MOBILE_TEST_BASE', 'http://127.0.0.1:5000')

# Prefer environment variables so secrets aren't hard-coded. Fallback to provided test creds.
SELLER = {
    'username': os.environ.get('MOBILE_TEST_USER', 'gitech'),
    'password': os.environ.get('MOBILE_TEST_PASS', 'gitech2025')
}

def main():
    print('Logging in...')
    r = requests.post(BASE + '/api/mobile/login', json=SELLER)
    print('Login status:', r.status_code)
    print(r.text)
    if r.status_code != 200:
        return
    token = r.json().get('token')
    headers = {'Authorization': 'Bearer ' + token}
    print('Fetching sorteos...')
    r2 = requests.get(BASE + '/api/mobile/sorteos', headers=headers)
    print('Sorteos status:', r2.status_code)
    print(r2.text)

if __name__ == '__main__':
    main()
