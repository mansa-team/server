- [ ] Implement an user management system so the user can customize its name, change password, profile picture and settings
- [ ] Make an Password Recovery Recovery system and 2FA using the Email Protocol

- [ ] Redis or some similar caching solution for the whole system

#

- [ ] Ma'at: Stock Picking algorithm designed to help build wallets for the users based on their profile and provide insights in the stocks page, such as its grade and recommended signal (Buy, Hold or Sell) based on Value Investing fundamentals
- [ ] Thoth: Wallet Management System for the users to be able to add and remove stocks from their wallet and add things such as goals, history of the wallet
- [ ] Ogum: Algo Trading System for the users with similar structure to how the ScraperService is executed, with scheduled tasks that will generate signals and then, calculate the specific needs for each user with Ogum enabled

#

- [ ] Fix all the security issues known to man already present in this repo in authentication and authorization

#

# User structure defined by string roles:
- **USER:** Standard access (Free)
- **PREMIUM:** Access to MUSA models and advanced algorithms
- **DEVELOPER:** Access to API Key generation and developer tab
- **ADMIN:** Full system access (All roles included)

*Note: Users can hold multiple roles simultaneously (e.g., "PREMIUM, DEVELOPER").*

#### USER:
- Access to Thoth and Ma'at

#### PREMIUM:
- Access to all MUSA's models and algorithms

#### DEVELOPER:
- Access to the API Key generation, being able to create an API key for his use

#

### STOCKS_API
- [ ] Dedicated key system linked to the main Mansa's structure (verify the userId before being able to create a key)

### Prometheus
- [ ] CORS environment validation to prevent API requests outside the website