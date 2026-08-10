- [ ] OpenUI and shadcn/ui

- [ ] Upload and Serve endpoints for files in the workspace
- [ ] Make the user able to manage their files in the workspace via endpoints related to workspace management /worksapce
  
- [ ] Github OAuth
- [ ] Implement an user management system so the user can customize its name, change password, profile picture and settings
- [ ] Make an Password Recovery system and 2FA using the Email Protocol

- [ ] Use the ForgeVM architecture to expose MetaTrader5 terminals

- [ ] Abacate Pay
- [ ] nginx sacling for autoscaling workers with tailored configs triggering the required services only (support for remote vps's)
- [ ] forgevm scaling via multiple hosts, simple router in business code and hostId tracking in the prometheus_sandbox model to select a host for the sandbox, rclone for /workspace cloning
- [ ] drop {service_name}_PORT and {serivce_name}_HOST and replace it with nginx managed services
- [ ] p99 latency and context switches monitor at /status
- [ ] feather cache for synced cache and with redis for a flock replacement

#

- [ ] Ma'at: Stock Picking algorithm designed to help build wallets for the users based on their profile and provide insights in the stocks page, such as its grade and recommended signal (Buy, Hold or Sell) based on Value Investing fundamentals
    - [ ] Use the inverse stocks corr matrix to recommend stocks if they are with an score of 75 >
- [ ] Thoth: Wallet Management System for the users. 
    - [ ] Import/Export via .xlsx (B3 Portal) or use get_positions() from MT5
- [ ] Ogum: Algo Trading System for the users.
    - [ ] Execution engine via MetaTrader 5 (MT5) for XP/BTG/Genial accounts
    - [ ] Notification/Deep Link system for manual execution in non-MT5 brokers (Inter, Nubank, Itaú)
    - [ ] Integration with Iniciador (Iniciação de Pagamentos) when support for B3 operations come through

#

# User structure defined by string roles:
- **USER:** Standard access (Free)
- **PREMIUM:** Access to MUSA models and advanced algorithms
- **DEVELOPER_STARTUP:** Explanation below
- **DEVELOPER_ENTERPRISE:** Explanation below
- **ADMIN:** Full system access (All roles included)

*Note: Users can hold multiple roles simultaneously (e.g., "PREMIUM, DEVELOPER").*

#### USER:
- Access to Thoth and Ma'at

#### PREMIUM:
- Access to all MUSA's models and algorithms

#### DEVELOPER:
- Access to the API Key generation, being able to create an API key for his use
    - [ ] **STARTUP (R$ 67/month):**
        - 10k API Calls / Month
        - Full access to all fundamental data (P/L, P/VP, ROE, DY, Investing Score, etc.)
        - Complete historical data (10+ years)
        - No custom field selection
        - 1 active API keys
        - Community support (forum, documentation)
        - Rate limit: 30 requests per minute
        - Basic data exports (CSV/JSON)
        - Usage Dashboard
        - Attribution required: "Data provided by Mansa"
        - Monthly billing, cancel anytime
    
    - [ ] **ENTERPRISE (R$ 679/month):**
        - Unlimited API calls (fair use policy)
        - Custom field/indicator requests
        - 5 active API keys
        - Priority support (telegram/inapp chat)
        - Rate limit: 300 requests per minute
        - Advanced bulk data exports
        - No attribution required
        - 2 Free Months in the annual plan (R$6790 per year)

#

Renaming ideas:
- Xango - Scraper / Stock Grading algorithm
- Oxossi - Portfolio Optimizer
- Iyagba - Wallet Manager
- Ogum - Automated Trading System
- Orunmila - Chatbot