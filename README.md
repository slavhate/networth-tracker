# Net Worth Tracker

A professional, full-featured web application for tracking personal net worth with a beautiful visualization dashboard. Features Indian Rupee (INR) currency support, dark mode, and comprehensive financial visualization.

![Net Worth Tracker](https://img.shields.io/badge/version-2.0.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Vibe Coded](https://img.shields.io/badge/vibe%20coded-with%20Claude-blueviolet.svg)
[![Docker Hub](https://img.shields.io/docker/pulls/shri32msi/networth-tracker?logo=docker&label=Docker%20Hub)](https://hub.docker.com/r/shri32msi/networth-tracker)

![Net Worth Dashboard](/images/dashboard.png)

## About This Project

- **Vibe Coded with Claude** - This entire project was vibe coded with the help of Claude AI (Anthropic)
- **100% Local & Private** - The web app runs entirely in containers on your local machine, ensuring your sensitive financial data never leaves your system
- **Personal Use Only** - This is a pet project, not a production-grade implementation. Use it for personal tracking only
- **Manual Data Entry** - No external connectors or bank sync. All data is manually entered and stays local. The only external data fetched is live stock prices from public market APIs (Yahoo Finance)

## Features

### Core Features
- **User Authentication** - Secure JWT-based authentication with registration and login
- **Two-Factor Authentication** - Optional TOTP 2FA (Google Authenticator, Authy, 1Password, ...) with one-time backup codes, managed from the Security page
- **Change Password** - Change your password from the Security page; your other signed-in devices are signed out
- **Dark Mode** - Toggle between light and dark themes
- **Privacy Mode** - Mask all financial numbers with one click (default ON for security)
- **Backup & Restore** - Download all your financial data as JSON. Restore replaces everything in your account with a backup, after showing what will change and offering to download your current data first. The whole file is validated before anything is written.
- **Last Updated Timestamp** - Shows when data was last refreshed in the sidebar
- **Responsive Design** - Works beautifully on desktop and mobile
- **Containerized** - Easy deployment with Docker

### Asset & Liability Management
- **Asset Management** - Track all your assets with categories (Cash & Savings, Investments, Real Estate, Vehicles, EPF, PPF, NPS, Other retirement, Gold, Sovereign Gold Bonds, Bonds, ESOP / RSU, Cryptocurrency, Other)
- **Liability Tracking** - Manage debts with interest rate tracking (Mortgage, Car Loan, Student Loan, Credit Card, Personal Loan)
- **Yearly Change Rates** - Give an asset a yearly change rate and it revalues itself every day from the last value and date you entered: vehicles depreciate, property appreciates. Picking Vehicles or Real Estate suggests a rate (-15% and +5%) that you can change or clear
- **EPF & PPF** - Enter the balance as it stands on a date (the passbook or statement balance, including the interest earned up to then), a monthly contribution and the interest rate, and the tracker grows it to today. Contributions count from the month after the balance date. Interest is worked out monthly on the running balance and credited every 31 March. Re-enter the balance and its date from each annual statement and the figures stay exact. Contribution changes start from today (the edit form moves the balance to today's value and today's date for you), while a rate change applies from the balance date
- **NPS** - Enter the balance as it stands on a date (from your statement), the contributions and, optionally, the schemes your money is invested in:
  - **Contributions** - The employer contribution per month and your own contribution per year (with the month you pay it, March by default). Both count from the month after the balance date, on the 1st of each month
  - **Investment options** - Pick schemes from the NPS list, give the % of new money each one gets (they must add up to 100%) and, optionally, the units from your statement (for every scheme or for none)
  - **How the value is worked out** - With statement units, those are the units held. Without them, the balance is split by the % and divided by each scheme's NAV on the balance date. Each contribution buys units at the NAV on its date. The value is units × the latest NAV, and contributions since the last refresh count at cost
  - **NAV refresh** - The Assets page refreshes the NAVs in the background when it loads, and each NPS card has a Refresh NAV button. Saving never fails because of the NAV service: if it is down, the asset is saved without prices and priced on the next refresh. If the NAVs come back but can't price the account (for example a scheme has no NAV on or before the balance date), it is saved without prices too, with a message saying why (use a later balance date), and Refresh NAV shows the same reason
  - **Without NAVs** - The value is the balance plus the contributions, grown at the expected return when one is set
  - **Asset classes** - Scheme E counts as equity, schemes C and G as debt, scheme A as other, and any other scheme (government, Lite, Vatsalya) splits 50/50. An NPS asset without schemes splits 50/50 too
  - **Changing contributions** - Unlike EPF and PPF, this doesn't move the balance to today. When your contributions change, update the balance, its date and the units from your latest statement
  - NAVs from npsnav.in (data from the NPS CRA, CC BY-NC 4.0; personal use)
- **Quantity × Price** - Gold, SGB and ESOP/RSU can be entered as a quantity and a price (per gram for gold and SGB, per share or unit for ESOP/RSU), and the value is quantity × price
- **EMI Loans** - Give a loan its EMI, or just its tenure and the EMI is worked out (rounded up to the paisa), and the tracker pays it down for you:
  - Today's outstanding balance, which is what counts toward net worth
  - Payoff date and the interest still left to pay
  - How your next EMI splits between interest and principal
  - A year-by-year schedule of the remaining payments
  - A red warning when the EMI doesn't even cover the interest
  - Made a prepayment? Update the balance and its date and the loan carries on from there
  - Rate, EMI or tenure revised? The change starts from the last EMI date, not the original balance date (the edit form re-anchors the balance there automatically, so a tenure counts the months left from then)

### Financial Sections
- **Bank Accounts** - Track savings, current, salary, fixed deposit (FD) and recurring deposit (RD) accounts across banks
  - **FD & RD Interest** - Add an interest rate and dates and a deposit grows with quarterly compounding, the way Indian banks quote it. The list shows today's value, the maturity value and how many days are left
  - **Deposits Maturing** - The dashboard shows a "deposits maturing" card for any FD or RD that matures within 30 days or has already matured
- **Insurances** - Manage life, health, term, vehicle, and property insurance policies with premium tracking (monthly/yearly frequency support)
- **Mutual Funds** - Track mutual fund investments with:
  - **Auto NAV Fetching** from mfapi.in (free API, no rate limits)
  - **Auto-calculated Avg NAV** (Invested Amount ÷ Units)
  - Current NAV tracking (fetched from internet)
  - Auto-calculation of current value from units × current NAV
  - "Refresh NAV" button to update all fund values
  - **SIPs** - Give a fund a SIP with its amount, frequency (monthly by default, or weekly or quarterly), the day of the month each installment lands (monthly and quarterly), the first and, optionally, the last installment date, and the date its units and invested amount are "as of" (today by default). Each installment after that date buys units at its day's NAV (mfapi.in, the latest NAV on or before the day), and the fund's units, invested amount and value count them. Installments since the last refresh count at cost until the NAVs are fetched. The Mutual Funds page refreshes SIP funds in the background when it loads, and saving never fails because of the NAV service: if it is down, the fund is saved unpriced and priced on the next refresh. To stop a SIP, clear its amount (or give it a last date). A change to the SIP's amount, frequency or day, or stopping it, applies from today: the server prices the installments made so far and adds their units and cost to the fund's units and invested amount as of today, so they keep the amount they were bought with (a stopped SIP keeps the units it bought) and the new SIP counts from today. This needs the NAVs, so if mfapi.in can't be reached the change is refused with a message to try again, rather than guessed. Changing the first or last SIP date corrects the schedule from the as-of date, and units, an invested amount or an as-of date you enter yourself are taken as given
- **Equities** - Stock portfolio management with:
  - Live price fetching from NSE, BSE, NASDAQ and NYSE via Yahoo Finance
  - Manual LTP (Last Traded Price) entry option
  - USD to INR conversion for US (NASDAQ and NYSE) stocks

### Dashboard & Goals
- **Net Worth Dashboard**:
  - Net Worth calculation and display
  - Asset allocation pie chart
  - Liability breakdown bar chart
  - Net worth history line chart
  - Allocation by asset class (equity, debt, gold, real estate, cash, other) and an allocation-history chart
  - Month-over-month change in net worth
  - Key metrics (Debt-to-Asset Ratio)
- **Net Worth Goal Tracker**:
  - Configurable target amount in Crores
  - Visual progress bar with milestone markers (25%, 50%, 75%, 100%)
  - Achievement tracking
  - Next milestone indicators
- **Snapshot History** - A snapshot is saved automatically the first time you open the dashboard once one is due (monthly by default; weekly, every 2 weeks or quarterly if you prefer), so your history builds up on its own; Save Snapshot adds extra points whenever you want one

### Currency & Localization
- **Indian Rupee (INR)** - Primary currency with proper Indian number formatting (lakhs, crores)
- **USD Support** - For US-listed (NASDAQ and NYSE) stocks
- **Live Exchange Rate** - USD to INR conversion fetched from free APIs (exchangerate-api.com, frankfurter.app) with 1-hour caching

## How Net Worth is Calculated

Your **Net Worth** is the total value of everything you own minus everything you owe. Here's what gets counted:

### What's Added (Your Assets)
- **Assets** - Cash, real estate, vehicles, retirement accounts (EPF, PPF, NPS), gold and Sovereign Gold Bonds, bonds, ESOP / RSU, cryptocurrency, and other valuables you've added, valued as of today (an asset with a yearly change rate is revalued from its last entered value)
- **Bank Accounts** - The total value across all your savings, current, salary, and deposit accounts (an FD or RD with an interest rate and dates includes the interest earned so far)
- **Mutual Funds** - The current value of all your mutual fund investments (units × current NAV, including the units your SIP installments have bought)
- **Equities (Stocks)** - The current market value of your stock portfolio. For US stocks (NASDAQ and NYSE), the value is automatically converted from USD to INR using live exchange rates

### What's Subtracted (Your Debts)
- **Liabilities** - All your debts including home loans, car loans, personal loans, credit card balances, and any other money you owe (a loan with an EMI counts today's outstanding balance)

### The Formula
**Net Worth = (Assets + Bank Accounts + Mutual Funds + Stocks) - Liabilities**

### What's NOT Included
- **Insurance Policies** - These are tracked separately for reference but don't count toward net worth since they represent future coverage, not current value

### Allocation by Asset Class
Alongside the breakdown by where an asset sits (category), the dashboard shows what it is, by **asset class**. Each holding counts toward one class, except NPS and hybrid mutual funds, which are split because their real mix varies (hybrid funds 50/50 between equity and debt; an NPS asset by its schemes, as described under NPS above, or 50/50 when it has none):

| Class | What counts |
|-------|-------------|
| Equity | Stocks, equity / ELSS / index mutual funds, ESOP / RSU, NPS scheme E, and half of hybrid funds and of NPS money not in an E, C, G or A scheme |
| Debt | EPF, PPF, bonds, retirement accounts, FDs and RDs, debt / liquid mutual funds, NPS schemes C and G, and half of hybrid funds and of NPS money not in an E, C, G or A scheme |
| Gold | Gold and Sovereign Gold Bonds |
| Real estate | Real estate |
| Cash | Cash and savings / current / salary accounts |
| Other | Investments, vehicles, cryptocurrency, NPS scheme A, other assets and funds, and anything without a known category |

### Snapshots
- A snapshot records your total assets, total liabilities and net worth on a date, together with the breakdown by category and by asset class, so past allocations can be charted.
- A snapshot is saved automatically the first time the dashboard is opened once one is due, dated that day. You choose how often, and each frequency is decided like this:
  - **Weekly** and **every 2 weeks**: due 7 or 14 days after your latest snapshot (the first one is due straight away).
  - **Monthly** (the default): one per calendar month, due on the 1st of the next month once this month has one.
  - **Quarterly**: one per calendar quarter (January to March, April to June, July to September, October to December), due on the first day of the next quarter once this quarter has one.
  - A snapshot you save yourself counts toward the schedule, snapshots dated in the future are ignored, and an account with nothing in it is skipped.
- **Save Snapshot** on the dashboard opens a dialog with the frequency selector, the date the next automatic snapshot is due, the date of your latest snapshot and a button to save one now. The frequency is also available at `GET` and `PUT /api/settings/snapshots` (`{"frequency": "weekly" | "fortnightly" | "monthly" | "quarterly"}`).
- The frequency is a per-user setting. It is not part of backups, so a restore leaves it as it is, and a new user starts on monthly.
- A snapshot saved from the dialog adds an extra point at any time. The dashboard shows the month-over-month change in net worth against the latest snapshot from an earlier month, and the allocation-history chart plots the class split of the snapshots over time.
- Snapshots taken before breakdowns were recorded keep only their totals; they still appear in the net worth history. Backups (export and restore) carry the breakdowns along.

## Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **Pydantic** - Data validation
- **JWT** - Authentication tokens
- **passlib + bcrypt** - Password hashing (bcrypt 4.0.1 pinned for compatibility)
- **httpx** - Async HTTP client for external API calls
- **External APIs**:
  - Yahoo Finance - Live stock prices (NSE, BSE, NASDAQ, NYSE)
  - mfapi.in - Mutual fund NAV data (free, no API key required)
  - Exchange Rate APIs - Live USD to INR conversion
- **When a source fails** - A price or NAV source that can't be reached (or answers with data that can't be used) never stops a save: the app carries on with what it already knows (the purchase or last fetched NAV, the last known price or rate, SIP installments and NPS contributions at cost) and says so. The API sends these warnings with the response, whatever its status, in an `X-Warnings` header: a JSON array of short messages, ASCII-encoded, exposed to cross-origin frontends and kept under 2,000 bytes (messages that don't fit become one "…and N more warnings"). A refresh that misses several funds or stocks sends one message naming a few of them. The frontend shows each message as a dismissible amber toast in the top-right corner that hides on its own after 15 seconds; up to three show at once, and the rest wait behind a "+N more warnings" line with a Dismiss all button

### Frontend
- **React 18** - UI framework
- **Vite** - Build tool
- **Tailwind CSS** - Styling with dark mode support
- **Recharts** - Charts and visualizations
- **Lucide React** - Icons
- **Axios** - HTTP client
- **React Router** - Navigation
- **Context API** - Theme, auth, and privacy state management

### Infrastructure
- **Docker** - Containerization
- **Docker Compose** - Multi-container orchestration
- **Nginx** - Production web server

## Docker Hub

Pre-built images are available on Docker Hub: [`shri32msi/networth-tracker`](https://hub.docker.com/r/shri32msi/networth-tracker)

| Tag | Description |
|-----|-------------|
| `backend` | FastAPI Python API server (port 8000) |
| `frontend` | React + Nginx static server (port 3000, proxies /api to backend) |

### Quick Start with Docker Run

```bash
# 1. Create a shared network
docker network create networth-network

# 2. Create a data directory
mkdir -p ./data

# 3. Start the backend (the frontend's nginx reaches it by the network alias "backend")
docker run -d \
  --name networth-backend \
  --network networth-network \
  --network-alias backend \
  -p 127.0.0.1:8000:8000 \
  -v ./data:/app/data \
  -e CREATE_DEMO_DATA=true \
  -e DATA_FILE=/app/data/data.json \
  shri32msi/networth-tracker:backend

# 4. Start the frontend
docker run -d \
  --name networth-frontend \
  --network networth-network \
  -p 3000:3000 \
  shri32msi/networth-tracker:frontend
```

Open http://localhost:3000 and log in as the demo user (**demo** by default, or your `DEMO_USERNAME`) with the password printed in the backend log (`docker logs networth-backend 2>&1 | grep "demo user"`) or the one you set in `DEMO_PASSWORD`. The password is only set when the demo user is first created: an existing data file keeps its password (change it in Settings).

```bash
# Stop and cleanup
docker stop networth-frontend networth-backend
docker rm networth-frontend networth-backend
docker network rm networth-network
```

### Quick Start with Docker Compose

```yaml
# docker-compose.yml
services:
  backend:
    image: shri32msi/networth-tracker:backend
    container_name: networth-backend
    ports:
      - "127.0.0.1:8000:8000"   # this machine only; browsers reach the API through the frontend's nginx
    volumes:
      - ./data:/app/data
    environment:
      - CREATE_DEMO_DATA=false   # true: create a demo user with sample data
      # - ALLOW_REGISTRATION=false   # once you have registered: nobody else can sign up
      # - DEMO_PASSWORD=   # optional; if unset, a random password is printed in the backend log
      - DATA_FILE=/app/data/data.json
      # Optional: set for persistent JWT sessions across restarts
      # - SECRET_KEY=   # optional; generate one with: openssl rand -hex 32
      # - TZ=IST-5:30   # optional: use Indian time for "today" (POSIX form works without tzdata)
    restart: unless-stopped

  frontend:
    image: shri32msi/networth-tracker:frontend
    container_name: networth-frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend
    restart: unless-stopped

networks:
  default:
    name: networth-network
```

```bash
docker compose up -d
```

Open http://localhost:3000 and register an account. To look around with sample data first, set `CREATE_DEMO_DATA=true`, then log in as the demo user (**demo** by default, or your `DEMO_USERNAME`) with the password printed in the backend log (`docker logs networth-backend 2>&1 | grep "demo user"`) or the one you set in `DEMO_PASSWORD`. The password is only set when the demo user is first created: an existing data file keeps its password (change it in Settings).

## Quick Start (Build from Source)

### Using Docker (Recommended)

1. **Clone and navigate to the project:**
   ```bash
   cd networth-tracker
   ```

2. **Start the application:**
   ```bash
   docker-compose up --build
   ```

3. **Access the application:**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000 (published on this machine only, 127.0.0.1)
   - API Docs: http://localhost:8000/docs

4. **Demo login** (`docker-compose.yml` ships with `CREATE_DEMO_DATA=false`; set it to `true` for a demo user):
   - Username: `demo` (or your `DEMO_USERNAME`)
   - Password: the one printed in the backend log (`docker logs networth-backend 2>&1 | grep "demo user"`), or the one you set in `DEMO_PASSWORD`

   The password is only set when the demo user is first created: an existing data file keeps its password (change it in Settings).

   The demo account comes pre-loaded with sample data across all sections.

### Local Development

#### Backend

1. **Create virtual environment:**
   ```bash
   cd backend
   python -m venv venv
   venv\Scripts\activate  # Windows
   # source venv/bin/activate  # Linux/Mac
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the server:**
   ```bash
   uvicorn main:app --reload --port 8000
   ```

#### Frontend

1. **Install dependencies:**
   ```bash
   cd frontend
   npm install
   ```

2. **Run development server:**
   ```bash
   npm run dev
   ```

3. **Access at:** http://localhost:3000

## Project Structure

```
networth-tracker/
├── backend/
│   ├── main.py           # FastAPI application & routes
│   ├── models.py         # Pydantic models for all entities
│   ├── auth.py           # Authentication utilities
│   ├── database.py       # JSON file database operations
│   ├── valuation.py      # What each holding is worth today: revaluation, FD/RD interest, loan amortization, totals
│   ├── restore.py        # Backup validation for restore
│   ├── stock_service.py  # Yahoo Finance stock price fetching
│   ├── nav_service.py    # Mutual fund NAV fetching from mfapi.in
│   ├── nps_service.py    # NPS scheme list and NAV history from npsnav.in
│   ├── exchange_service.py # Live USD/INR exchange rate
│   ├── config.py         # Configuration settings
│   ├── requirements.txt  # Python dependencies
│   └── Dockerfile        # Backend container config
├── frontend/
│   ├── src/
│   │   ├── components/   # Reusable components (Layout, ProtectedRoute)
│   │   ├── pages/        # Page components
│   │   │   ├── Dashboard.jsx    # Main dashboard with goal card
│   │   │   ├── Assets.jsx       # Asset management
│   │   │   ├── Liabilities.jsx  # Liability management
│   │   │   ├── BankAccounts.jsx # Bank account tracking
│   │   │   ├── Insurances.jsx   # Insurance policy management
│   │   │   ├── MutualFunds.jsx  # Mutual fund tracking
│   │   │   ├── Equities.jsx     # Stock portfolio with live prices
│   │   │   ├── Login.jsx        # Login page
│   │   │   └── Register.jsx     # Registration page
│   │   ├── App.jsx       # Main app component with routing
│   │   ├── api.js        # API client for all endpoints
│   │   ├── AuthContext.jsx   # Auth state management
│   │   ├── ThemeContext.jsx  # Dark mode state management
│   │   ├── PrivacyContext.jsx # Privacy mode state management
│   │   └── index.css     # Tailwind styles
│   ├── package.json      # Node dependencies
│   ├── vite.config.js    # Vite configuration
│   ├── tailwind.config.js # Tailwind configuration with dark mode
│   ├── nginx.conf        # Production nginx config
│   └── Dockerfile        # Frontend container config
├── data/
│   └── data.json         # JSON file storage (users, assets, liabilities, etc.)
├── docker-compose.yml    # Container orchestration
└── README.md
```

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new user (403 when `ALLOW_REGISTRATION=false`) |
| POST | `/api/auth/login` | Login and get token (returns a 2FA challenge when 2FA is on; 429 after too many failed attempts) |
| POST | `/api/auth/login/2fa` | Complete a 2FA login with an authenticator or backup code |
| GET | `/api/auth/me` | Get current user info |
| GET | `/api/auth/2fa/status` | Whether 2FA is on and how many backup codes remain |
| POST | `/api/auth/2fa/setup` | Start 2FA enrollment (returns secret + otpauth URI) |
| POST | `/api/auth/2fa/enable` | Confirm enrollment with your password and a code; returns backup codes once |
| POST | `/api/auth/2fa/disable` | Turn off 2FA (requires password + code) |
| POST | `/api/auth/password` | Change your password (current password, plus a code if 2FA is on); signs out other sessions |

> **Locked out of 2FA?** If a user has lost both their authenticator and their backup codes, stop the app, open `data/data.json`, and remove that user's `totp_*` and `backup_code_hashes` fields. They can then sign in with just their password.

### Assets
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/assets` | List all assets |
| POST | `/api/assets` | Create new asset |
| GET | `/api/assets/{id}` | Get asset by ID |
| PUT | `/api/assets/{id}` | Update asset |
| DELETE | `/api/assets/{id}` | Delete asset |
| POST | `/api/assets/{id}/refresh-nav` | Price an NPS asset's schemes again with the latest NAVs (400 without NPS schemes, 502 when the NAVs can't be fetched) |
| GET | `/api/nps/schemes` | Every NPS scheme with its latest NAV, for choosing investment options (502 when the list can't be fetched) |

### Liabilities
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/liabilities` | List all liabilities |
| POST | `/api/liabilities` | Create new liability |
| GET | `/api/liabilities/{id}` | Get liability by ID |
| PUT | `/api/liabilities/{id}` | Update liability |
| DELETE | `/api/liabilities/{id}` | Delete liability |
| GET | `/api/liabilities/{id}/schedule` | Year-by-year schedule of the remaining EMIs (400 if the liability has no EMI) |

### Bank Accounts
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/bank-accounts` | List all bank accounts |
| POST | `/api/bank-accounts` | Create new bank account |
| GET | `/api/bank-accounts/{id}` | Get bank account by ID |
| PUT | `/api/bank-accounts/{id}` | Update bank account |
| DELETE | `/api/bank-accounts/{id}` | Delete bank account |

### Insurances
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/insurances` | List all insurance policies |
| POST | `/api/insurances` | Create new insurance policy |
| GET | `/api/insurances/{id}` | Get insurance by ID |
| PUT | `/api/insurances/{id}` | Update insurance policy |
| DELETE | `/api/insurances/{id}` | Delete insurance policy |

### Mutual Funds
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/mutual-funds` | List all mutual fund holdings |
| POST | `/api/mutual-funds` | Create new mutual fund entry |
| GET | `/api/mutual-funds/{id}` | Get mutual fund by ID |
| PUT | `/api/mutual-funds/{id}` | Update mutual fund entry (409 if the fund changed while its NAVs were being fetched) |
| DELETE | `/api/mutual-funds/{id}` | Delete mutual fund entry |
| POST | `/api/mutual-funds/{id}/refresh-nav` | Refresh NAV for specific fund (and price its SIP up to today) |
| GET | `/api/nav/search?q={query}` | Search mutual funds by name (signed in; `q` up to 150 characters) |
| GET | `/api/nav/test` | Test NAV service connectivity (signed in) |

### Equities (Stocks)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/equities` | List all stock holdings |
| POST | `/api/equities` | Add new stock holding |
| GET | `/api/equities/{id}` | Get stock by ID |
| PUT | `/api/equities/{id}` | Update stock holding |
| DELETE | `/api/equities/{id}` | Delete stock holding |
| POST | `/api/equities/refresh-prices` | Refresh all stock prices from Yahoo Finance |

### Dashboard & Goals
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/dashboard` | Get dashboard metrics (saves an automatic snapshot on the first visit once one is due; includes `snapshot_frequency` and `next_snapshot_on`) |
| POST | `/api/snapshot` | Create net worth snapshot, with its breakdown |
| GET | `/api/settings/snapshots` | Get how often automatic snapshots are saved and when the next is due |
| PUT | `/api/settings/snapshots` | Set the automatic snapshot frequency (`weekly`, `fortnightly`, `monthly` or `quarterly`) |
| GET | `/api/goal` | Get user's net worth goal |
| POST | `/api/goal` | Create net worth goal |
| PUT | `/api/goal` | Update net worth goal |
| DELETE | `/api/goal` | Delete net worth goal |
| GET | `/api/exchange-rate` | Get current USD to INR rate |
| GET | `/api/export` | Export all user data as JSON backup |
| POST | `/api/restore` | Replace all your data with a backup file (multipart field `file`) |

## Data Storage

The application uses a simple JSON file for data storage (`data/data.json`), making it perfect for personal use without the overhead of a database server. The file persists data even when containers are restarted through Docker volume mounting. `data.json` is saved atomically (written to a temporary file in the same folder, then renamed over the original), so the data folder itself must be writable by the backend's user, not just the file.

### Data Collections
- **users** - User accounts with hashed passwords
- **assets** - Physical and financial assets
- **liabilities** - Debts and loans
- **snapshots** - Historical net worth snapshots
- **bank_accounts** - Bank account details
- **insurances** - Insurance policies
- **mutual_funds** - Mutual fund holdings
- **equities** - Stock portfolio with market info
- **goals** - Net worth target goals (per user)

## Security

- Passwords hashed using bcrypt (in a worker thread, so a login never holds up other requests); an unknown username takes as long to reject as a wrong password
- Failed logins are limited in memory, within 15 minutes: 5 for one username from one client, 50 for one username from all clients together, and 20 from one client across all usernames. Past a limit the login answers `429 Too Many Requests` with a `Retry-After` header. Wrong 2FA codes count too, and a successful login clears the username's counts. The 5 is per client so that someone guessing from elsewhere can't lock you out with five requests; the looser total of 50 still stops a guesser spread over many addresses. An IPv6 client is counted by its /64, which a home or host usually gets whole. The counts reset when the backend restarts
- The client address for these limits is the connecting address, except for a peer listed in `TRUSTED_PROXIES` (by default `172.16.0.0/12`, the range Docker gives bridge networks such as the compose network, where the bundled nginx runs): from such a proxy the backend takes its `X-Real-IP`, or else the nearest untrusted address in `X-Forwarded-For`. Anything else that reaches port 8000 is counted as itself, whatever headers it sends
- Registration can be closed with `ALLOW_REGISTRATION=false` once your account exists
- JWT tokens for stateless authentication (secret auto-generated or via env var)
- CORS restricted to specific origins, methods (`GET`, `POST`, `PUT`, `DELETE`, `OPTIONS`), and headers (`Authorization`, `Content-Type`)
- Token expiration after 24 hours
- Non-root container users
- Nginx security headers on every response, static files included (`frontend/security-headers.conf`): `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, a `Permissions-Policy` that turns off camera, microphone, geolocation, payment and USB, and a `Content-Security-Policy` that allows scripts, styles, fonts, images and API calls from the app's own origin only (no inline or third-party scripts; inline styles are allowed for the charts, images may also be `data:` URLs; no plugins, no framing by other sites, forms post only to the app). nginx doesn't reveal its version (`server_tokens off`)
- Restore upload size limit (10MB, read in chunks so a larger upload is turned away without being held in memory); every item is validated before anything is written
- Text fields have length limits (notes and descriptions 2,000 characters, short labels 100) so no request can bloat the data file
- The data file is created readable by its owner only (0600)
- `docker-compose.yml` publishes the backend's port 8000 on 127.0.0.1 only; everything else goes through nginx
- Stock prices from Yahoo Finance must be a finite number above zero (and within the amount limit) to be stored; anything else counts as unavailable
- Every number must be finite and within sane limits (amounts up to 10^15), whether it is typed in or comes from a restored backup; asset valuation, loan balance and FD/RD start and maturity dates must be real calendar dates (YYYY-MM-DD)
- Demo data opt-in via `CREATE_DEMO_DATA` environment variable; the demo user gets a random password (printed once in the backend log) unless you set `DEMO_PASSWORD`

## Stock Market Integration

The Equities module supports live stock price fetching via Yahoo Finance:

| Market | Symbol Format | Currency | Example |
|--------|--------------|----------|---------|
| NSE (India) | `SYMBOL.NS` | INR | RELIANCE.NS |
| BSE (India) | `SYMBOL.BO` | INR | RELIANCE.BO |
| NASDAQ (US) | `SYMBOL` | USD | AAPL |
| NYSE (US) | `SYMBOL` | USD | KO |

Click "Refresh Prices" on the Equities page to fetch the latest stock prices.

## Environment Variables

### Backend
| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | _(auto-generated)_ | JWT signing key. Set for persistent sessions across restarts; use at least 32 random characters (a shorter key logs a warning at startup). The auto-generated key is per process, so without `SECRET_KEY` run a single worker (no `uvicorn --workers`) |
| `CREATE_DEMO_DATA` | `false` | Set to `true` to create demo user with sample data on startup (`docker-compose.yml` sets `false` too) |
| `ALLOW_REGISTRATION` | `true` | Set to `false` to turn off sign-up (`POST /api/auth/register` returns 403); existing users can still log in |
| `TRUSTED_PROXIES` | `172.16.0.0/12` | Comma-separated addresses or networks (CIDR) of reverse proxies whose `X-Real-IP` / `X-Forwarded-For` headers name the client, for the failed-login limits. The default is Docker's bridge-network range, which holds the bundled docker-compose nginx, so compose works as is. Narrow it to nginx's address if other containers or the Docker host can reach port 8000 (anything in the list can claim any client address), or set your proxy's address when you run the backend another way |
| `DEMO_USERNAME` | `demo` | Username of the demo user |
| `DEMO_PASSWORD` | _(random)_ | Password of the demo user. If unset, a random password is generated and printed once in the backend log. Only applied when the demo user is first created |
| `DATA_FILE` | `../data/data.json` | Path to the JSON database file |
| `NPS_NAV_API_URL` | `https://npsnav.in/api` | Base URL of the NPS scheme list and NAV API (npsnav.in). Point it at a mirror or a self-hosted copy of the same API |
| `TZ` | _(system timezone; UTC in Docker)_ | Timezone for "today", the date loan balances, FD/RD values and revalued assets are worked out for, and the month and date of automatic snapshots and of the snapshots you save. Near midnight a UTC server is still on the previous day in India; set `TZ=IST-5:30` (POSIX form, works without tzdata) to use Indian time |

### Frontend
| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `` | API base URL (empty for proxy) |

## Production Deployment

1. **Generate and set a secret key:**
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   Add it to `docker-compose.yml`:
   ```yaml
   environment:
     - SECRET_KEY=${SECRET_KEY}   # read from your shell or a .env file next to docker-compose.yml
   ```

2. **Disable demo data** (remove or set `CREATE_DEMO_DATA=false`) and, once you have registered, **close registration** with `ALLOW_REGISTRATION=false`

3. **Build and run:**
   ```bash
   docker-compose up --build -d
   ```

4. **Configure reverse proxy** (nginx/traefik) for HTTPS

   With another proxy in front of the bundled nginx, nginx sees that proxy as every request's address and passes it on in `X-Real-IP`, so all clients would share one failed-login count. Make nginx take the real client from the outer proxy: in the `server` block of `frontend/nginx.conf`, add `set_real_ip_from <outer proxy address or network>;` and `real_ip_header X-Forwarded-For;` (and `real_ip_recursive on;` if there are several proxies). nginx then puts the real client in `$remote_addr`, which it already sends as `X-Real-IP`. Have the outer proxy set `X-Forwarded-For` (nginx, traefik and Caddy do by default)

## License

MIT License - feel free to use this project for personal or commercial purposes.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
