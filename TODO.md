[ ] - Create an user authentication system
[ ] - Create an account preferences system
[ ] - Move the STOCKS API /key/generate out of the stocks_api service and integrate it a proper  own user management service
[ ] - Make an Password Recovery Recovery system and 2FA using the Email Protocol

[ ] - Create a chatbot history for Prometheus

[ ] - Ma'at: Stock Picking algorithm designed to help build wallets for the users based on their profile and provide insights in the stocks page, such as its grade and recommended signal (Buy, Hold or Sell) based on Value Investing fundamentals
[ ] - Thoth: Wallet Management System for the users to be able to add and remove stocks from their wallet and add things such as goals, history of the wallet
[ ] - Ogum: Algo Trading System for the users with similar structure to how the ScraperService is executed, with scheduled tasks that will generate signals and then, calculate the specific needs for each user with Ogum enabled

[ ] - Fix all the security issues known to man already present in this repo

- User structure defined by access levels:
    00: Free
    10: Premium
    01: Developer
    11: Premium and Developer
    67: Admin

Free User:
    - Access to Thoth and Ma'at

Premium User:
    - Access to all MUSA's models and algorithms

Developer:
    - Access to the API Key generation, being able to create an API key for his use

Premium and Developer:
    - Access to both Premium and Developer features