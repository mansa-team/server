from imports import *
from main.utils.util import log

def checkMYSQLConnection():
    try:
        startTime = time.time()

        with dbEngine.connect() as connection:
           connection.execute(text("SELECT 1"))
        
        latency = (time.time() - startTime) * 1000

        log("db", f"MYSQL connected ({latency:.2f}ms)")

        return True
    except Exception as e:
        log("db", f"MYSQL connection failed: {e}")

        return False
    
def checkServiceConnection(service: str):
    try:
        serviceConfig = getattr(Config, service, None)
        host = serviceConfig['HOST']
        port = serviceConfig['PORT']
    
        if service == "STOCKS_API": prefix = "stocks"
        if service == "Prometheus": prefix = "prometheus"

        startTime = time.time()
        response = requests.get(f"http://{host}:{port}/{prefix}/health", timeout=5)
        latency = (time.time() - startTime) * 1000

        if response.status_code == 200:
            log("service", f"{service} connected ({latency:.2f}ms)")
                
            return True
    except Exception as e:
        log("service", f"{service} connection failed: {e}\nDue to this issue the server couldn't start.")

        return False