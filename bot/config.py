import os
from dotenv import load_dotenv

# do the env variables
load_dotenv()

token = os.getenv('KEY')
apikey = os.getenv('API_KEY')
