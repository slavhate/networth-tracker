# Net Worth Tracker

A professional, full-featured web application for tracking personal net worth with a beautiful visualization dashboard. Features Indian Rupee (INR) currency support, dark mode, and comprehensive financial management.

![Net Worth Tracker](https://img.shields.io/badge/version-2.0.0-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Vibe Coded](https://img.shields.io/badge/vibe%20coded-with%20Claude-blueviolet.svg)

> **[View Sample Dashboard Screenshot](#)** *(Add your hosted screenshot link here)*

## About This Project

- **Vibe Coded with Claude** - This entire project was vibe coded with the help of Claude AI (Anthropic)
- **100% Local & Private** - The web app runs entirely in containers on your local machine, ensuring your sensitive financial data never leaves your system
- **Personal Use Only** - This is a pet project, not a production-grade implementation. Use it for personal tracking only
- **Manual Data Entry** - No external connectors or bank sync. All data is manually entered and stays local. The only external data fetched is live stock prices from public market APIs (Yahoo Finance)

## Features

### Core Features
- **User Authentication** - Secure JWT-based authentication with registration and login
- **Dark Mode** - Toggle between light and dark themes
- **Responsive Design** - Works beautifully on desktop and mobile
- **Containerized** - Easy deployment with Docker

### Asset & Liability Management
- **Asset Management** - Track all your assets with categories (Cash, Investments, Real Estate, Vehicles, Retirement, Crypto)
- **Liability Tracking** - Manage debts with interest rate tracking (Mortgage, Car Loan, Student Loan, Credit Card, Personal Loan)

### Financial Sections
- **Bank Accounts** - Track savings, current, salary, and fixed deposit accounts across banks
- **Insurances** - Manage life, health, term, vehicle, and property insurance policies with premium tracking
- **Mutual Funds** - Track mutual fund investments with NAV updates and returns calculations
- **Equities** - Stock portfolio management with live price fetching from NSE, BSE, and NASDAQ markets via Yahoo Finance

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

## Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **Pydantic** - Data validation
- **JWT** - Authentication tokens
- **passlib + bcrypt** - Password hashing (bcrypt 4.0.1 pinned for compatibility)
- **yfinance** - Live stock price fetching from Yahoo Finance (NSE, BSE, NASDAQ)

### Frontend
- **React 18** - UI framework
- **Vite** - Build tool
- **Tailwind CSS** - Styling with dark mode support
- **Recharts** - Charts and visualizations
- **Lucide React** - Icons
- **Axios** - HTTP client
- **React Router** - Navigation
- **Context API** - Theme and auth state management

### Infrastructure
- **Docker** - Containerization
- **Docker Compose** - Multi-container orchestration
- **Nginx** - Production web server

## Quick Start

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

4. **Demo credentials:**
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

- Passwords are hashed using bcrypt
- JWT tokens for stateless authentication
- CORS configured for frontend origin
- Token expiration after 24 hours

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
| `SECRET_KEY` | (set in config) | JWT signing key |
| `DATA_FILE` | `../data/data.json` | Path to data file |

### Frontend
| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `` | API base URL (empty for proxy) |

## Production Deployment

1. **Update the secret key** in `docker-compose.yml`:
   ```yaml
   environment:
     - SECRET_KEY=your-very-secure-random-secret-key
   ```

2. **Build and run:**
   ```bash
   docker-compose up --build -d
   ```

3. **Configure reverse proxy** (nginx/traefik) for HTTPS

## License

MIT License - feel free to use this project for personal or commercial purposes.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
