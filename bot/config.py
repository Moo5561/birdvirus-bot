import os
from dotenv import load_dotenv

# do the env variables
load_dotenv()

token = os.getenv('KEY')
apikey = os.getenv('API_KEY')

# bot owners — always pass is_admin/is_bot_dev and can force the bot out of a vc
OWNER_IDS = frozenset({
    1048423590623727686,
    1278489064210956378,
    1421940246492352612,
    1246945967102623755,
    1488967988207157308,
    274556515061465088,
    983544114635235430,
})

# the nightly/dev bot: different prefix, separate db, bypasses economy checks
NIGHTLY_BOT_ID = 1522117141090799697
