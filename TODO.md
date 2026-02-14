[ ] - Create an user authentication system
[ ] - Create an account preferences system
[ ] - Move the STOCKS API /key/generate out of the stocks_api service and integrate it a proper  own user management service
[ ] - Make an Password Recovery Recovery system and 2FA using the Email Protocol

[ ] - Create a chatbot history for Prometheus
[ ] - Wallet Management System for the users to be able to add and remove stocks from their wallet and add things such as goals, history of the wallet and others
[ ] - Algo Trading System for the users included through the Wallet Management System with similar structure to how the ScraperService is executed

- User structure defined by access levels:
    00: Free (No access to Prometheus and the Algo Trader)
    10: Premium (Access to Prometheus and the Algo Trader)
    01: Developer (Access to the API Key generating system for the StocksAPI and has the same features as the Free User)
    11: Premium and Developer (Access to the Premium User features and the Developer features)
    67: Admin (TODO)

Free User:
    - Access to the Wallet System and the Stock Info

Premium User:
    - Access to the Stock Overview system with signal recommendations based on the Intrinsic Value
    - Access to the Prometheus chatbot system
    - Access to the Algo Trader

Developer:
    - Access to the API Key generation, being able to create an API key for his use

Premium and Developer:
    - Access to both Premium and Developer features