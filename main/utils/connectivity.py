import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from imports import *

def checkMYSQLConnection():
    try:
        startTime = time.time()

        with dbEngine.connect() as connection:
           connection.execute(text("SELECT 1"))
        
        latency = (time.time() - startTime) * 1000

        if Config.DEBUG_MODE == "TRUE":
            print(f"MYSQL connected ({latency:.2f}ms)")

        return True
    except Exception as e:
        if Config.DEBUG_MODE == "TRUE":
            print(f"MYSQL connection failed: {e}")

        return False
    
def checkServiceConnection(service: str):
    try:
        serviceConfig = getattr(Config, service, None)
        host = serviceConfig['HOST']
        port = serviceConfig['PORT']
    
        if service == "STOCKS_API": prefix = "stocks"
        if service == "Prometheus": prefix = "rag"

        startTime = time.time()
        response = requests.get(f"http://{host}:{port}/{prefix}/health", timeout=5)
        latency = (time.time() - startTime) * 1000

        if response.status_code == 200:
            if Config.DEBUG_MODE == "TRUE":
                print(f"{service} connected ({latency:.2f}ms)")
                
            return True
    except Exception as e:
        if Config.DEBUG_MODE == "TRUE":
            print(f"{service} connection failed: {e}" + "\nDue to this issue the server couldn't start.")

        return False