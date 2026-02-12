from imports import *

def mysqlConnectionTest():
    try:
        startTime = time.time()

        with dbEngine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            result.close()
        
        latency = (time.time() - startTime) * 1000

        print(f"MYSQL connected! ({latency:.2f}ms)")
        return True
    except Exception as e:
        print(f"MYSQL connection failed: {e}")
        return False
    
if __name__ == "__main__":
    while True: time.sleep(1)