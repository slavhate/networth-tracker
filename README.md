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
- **Dark Mode** - Toggle between light and dark themes
- **Privacy Mode** - Mask all financial numbers with one click (default ON for security)
- **Data Export/Backup** - Download all your financial data as JSON for backup purposes
- **Last Updated Timestamp** - Shows when data was last refreshed in the sidebar
- **Responsive Design** - Works beautifully on desktop and mobile
- **Containerized** - Easy deployment with Docker

### Asset & Liability Management
- **Asset Management** - Track all your assets with categories (Cash, Investments, Real Estate, Vehicles, Retirement, Crypto)
- **Liability Tracking** - Manage debts with interest rate tracking (Mortgage, Car Loan, Student Loan, Credit Card, Personal Loan)

### Financial Sections
- **Bank Accounts** - Track savings, current, salary, and fixed deposit accounts across banks
- **Insurances** - Manage life, health, term, vehicle, and property insurance policies with premium tracking (monthly/yearly frequency support)
- **Mutual Funds** - Track mutual fund investments with:
  - **Auto NAV Fetching** from mfapi.in (free API, no rate limits)
  - **Auto-calculated Avg NAV** (Invested Amount ÷ Units)
  - Current NAV tracking (fetched from internet)
  - Auto-calculation of current value from units × current NAV
  - "Refresh NAV" button to update all fund values
- **Equities** - Stock portfolio management with:
  - Live price fetching from NSE, BSE, and NASDAQ via Yahoo Finance
  - Manual LTP (Last Traded Price) entry option
  - USD to INR conversion for NASDAQ stocks

### Dashboard & Goals
- **Net Worth Dashboard**:
  - Net Worth calculation and display
  - Asset allocation pie chart
  - Liability breakdown bar chart
  - Net worth history line chart
  - Key metrics (Debt-to-Asset Ratio)
- **Net Worth Goal Tracker**:
  - Configurable target amount in Crores
  - Visual progress bar with milestone markers (25%, 50%, 75%, 100%)
  - Achievement tracking
  - Next milestone indicators
- **Snapshot History** - Save periodic snapshots to track your progress over time

### Currency & Localization
- **Indian Rupee (INR)** - Primary currency with proper Indian number formatting (lakhs, crores)
- **USD Support** - For NASDAQ-listed stocks
- **Live Exchange Rate** - USD to INR conversion fetched from free APIs (exchangerate-api.com, frankfurter.app) with 1-hour caching

## How Net Worth is Calculated

Your **Net Worth** is the total value of everything you own minus everything you owe. Here's what gets counted:

### What's Added (Your Assets)
- **Assets** - Cash, real estate, vehicles, retirement accounts, crypto, and other valuables you've added
- **Bank Accounts** - The total balance across all your savings, current, salary, and fixed deposit accounts
- **Mutual Funds** - The current value of all your mutual fund investments (units × current NAV)
- **Equities (Stocks)** - The current market value of your stock portfolio. For US stocks (NASDAQ), the value is automatically converted from USD to INR using live exchange rates

### What's Subtracted (Your Debts)
- **Liabilities** - All your debts including home loans, car loans, personal loans, credit card balances, and any other money you owe

### The Formula
**Net Worth = (Assets + Bank Accounts + Mutual Funds + Stocks) - Liabilities**

### What's NOT Included
- **Insurance Policies** - These are tracked separately for reference but don't count toward net worth since they represent future coverage, not current value

## Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **Pydantic** - Data validation
- **JWT** - Authentication tokens
- **passlib + bcrypt** - Password hashing (bcrypt 4.0.1 pinned for compatibility)
- **httpx** - Async HTTP client for external API calls
- **External APIs**:
  - Yahoo Finance - Live stock prices (NSE, BSE, NASDAQ)
  - mfapi.in - Mutual fund NAV data (free, no API key required)
  - Exchange Rate APIs - Live USD to INR conversion

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

# 3. Start the backend
docker run -d \
  --name networth-backend \
  --network networth-network \
  -p 8000:8000 \
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

Open http://localhost:3000 and login with **demo** / **password123**.

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
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - CREATE_DEMO_DATA=true
      - DATA_FILE=/app/data/data.json
      # Optional: set for persistent JWT sessions across restarts
      # - SECRET_KEY=your-secret-key-here
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

Open http://localhost:3000 and login with **demo** / **password123**.

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
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

4. **Demo credentials** (when `CREATE_DEMO_DATA=true`):
   - Username: `demo`
   - Password: `password123`

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
│   ├── stock_service.py  # Yahoo Finance stock price fetching
│   ├── nav_service.py    # Mutual fund NAV fetching from mfapi.in
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
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login and get token |
| GET | `/api/auth/me` | Get current user info |

### Assets
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/assets` | List all assets |
| POST | `/api/assets` | Create new asset |
| GET | `/api/assets/{id}` | Get asset by ID |
| PUT | `/api/assets/{id}` | Update asset |
| DELETE | `/api/assets/{id}` | Delete asset |

### Liabilities
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/liabilities` | List all liabilities |
| POST | `/api/liabilities` | Create new liability |
| GET | `/api/liabilities/{id}` | Get liability by ID |
| PUT | `/api/liabilities/{id}` | Update liability |
| DELETE | `/api/liabilities/{id}` | Delete liability |

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
| PUT | `/api/mutual-funds/{id}` | Update mutual fund entry |
| DELETE | `/api/mutual-funds/{id}` | Delete mutual fund entry |
| POST | `/api/mutual-funds/{id}/refresh-nav` | Refresh NAV for specific fund |
| GET | `/api/nav/search?q={query}` | Search mutual funds by name |
| GET | `/api/nav/test` | Test NAV service connectivity |

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
| GET | `/api/dashboard` | Get dashboard metrics |
| POST | `/api/snapshot` | Create net worth snapshot |
| GET | `/api/goal` | Get user's net worth goal |
| POST | `/api/goal` | Create net worth goal |
| PUT | `/api/goal` | Update net worth goal |
| DELETE | `/api/goal` | Delete net worth goal |
| GET | `/api/exchange-rate` | Get current USD to INR rate |
| GET | `/api/export` | Export all user data as JSON backup |

## Data Storage

The application uses a simple JSON file for data storage (`data/data.json`), making it perfect for personal use without the overhead of a database server. The file persists data even when containers are restarted through Docker volume mounting.

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

- Passwords hashed using bcrypt
- JWT tokens for stateless authentication (secret auto-generated or via env var)
- CORS restricted to specific origins, methods (`GET`, `POST`, `PUT`, `DELETE`, `OPTIONS`), and headers (`Authorization`, `Content-Type`)
- Token expiration after 24 hours
- Non-root container users
- Nginx security headers (X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy, Permissions-Policy)
- Import payload size limit (10MB)
- Demo data opt-in via `CREATE_DEMO_DATA` environment variable

## Stock Market Integration

The Equities module supports live stock price fetching via Yahoo Finance:

| Market | Symbol Format | Currency | Example |
|--------|--------------|----------|---------|
| NSE (India) | `SYMBOL.NS` | INR | RELIANCE.NS |
| BSE (India) | `SYMBOL.BO` | INR | RELIANCE.BO |
| NASDAQ (US) | `SYMBOL` | USD | AAPL |

Click "Refresh Prices" on the Equities page to fetch the latest stock prices.

## Environment Variables

### Backend
| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | _(auto-generated)_ | JWT signing key. Set for persistent sessions across restarts |
| `CREATE_DEMO_DATA` | `false` | Set to `true` to create demo user with sample data on startup |
| `DATA_FILE` | `../data/data.json` | Path to the JSON database file |

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
     - SECRET_KEY=your-generated-key-here
   ```

2. **Disable demo data** (remove or set `CREATE_DEMO_DATA=false`)

3. **Build and run:**
   ```bash
   docker-compose up --build -d
   ```

4. **Configure reverse proxy** (nginx/traefik) for HTTPS

## License

MIT License - feel free to use this project for personal or commercial purposes.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
