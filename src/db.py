"""Project-root .env settings; importing engine does not open a connection."""
from pathlib import Path
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, URL

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=False)

def make_engine():
    required = ['MYSQL_DATABASE', 'MYSQL_USER', 'MYSQL_PASSWORD']
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise ValueError('Missing environment variables: ' + ', '.join(missing))
    url = URL.create('mysql+pymysql', username=os.environ['MYSQL_USER'],
                     password=os.environ['MYSQL_PASSWORD'],
                     host=os.getenv('DB_HOST', 'localhost'), port=int(os.getenv('DB_PORT', '3306')),
                     database=os.environ['MYSQL_DATABASE'], query={'charset': 'utf8mb4'})
    return create_engine(url, pool_pre_ping=True, hide_parameters=True,
                         connect_args={'connect_timeout': 10})

engine = make_engine()
