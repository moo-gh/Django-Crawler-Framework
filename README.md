# Websites Crawler Framework

A powerful Django-based web crawling framework designed to monitor websites for new content and automatically notify users of updates. Perfect for real estate monitoring, news aggregation, job hunting, and any scenario where being first to discover new content provides an advantage.

## 🎯 Use Cases

- **Real Estate Monitoring**: Be the first to apply to new property listings
- **News Aggregation**: Get notified of new articles from your favorite websites
- **Job Hunting**: Monitor job boards for new opportunities
- **E-commerce**: Track new products or price drops
- **Content Monitoring**: Stay updated on blogs, forums, and social media

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone git@github.com:ghorbani-mohammad/crawler-framework.git
   cd crawler-framework
   ```

2. **Start the application**
   ```bash
   # Development
   docker-compose up
   
   # Production
   docker-compose -f docker-compose-prod.yml up
   ```

3. **Access the application**
   - Django Admin: `http://localhost:8000/secret-admin/`
   - API Endpoints: `http://localhost:8000/api/`

## 🏗️ Architecture Overview

This framework is built around three core entities that work together to create a comprehensive crawling solution:

### 1. Agency
**Definition**: Represents a website or domain you want to monitor
**Examples**: CNN, BBC, Digikala, LinkedIn Jobs

**Key Features**:
- Configure website-specific settings
- Set crawling intervals and timeouts
- Define proxy settings
- Configure notification preferences

### 2. Page
**Definition**: Specific pages within an agency that contain the content you want to monitor
**Examples**: CNN Politics page, BBC Technology section, Job listings page

**Key Features**:
- Define page-specific crawling rules
- Set up filtering and token management
- Configure scroll behavior for dynamic content
- Set message templates for notifications

### 3. Structure
**Definition**: Defines how to extract data from pages using CSS selectors and XPath
**Purpose**: Tells the crawler engine exactly what elements to look for and how to extract information

**Key Components**:
- **News Links Structure**: CSS selectors to find article/product links
- **Content Structure**: How to extract titles, descriptions, dates, etc.
- **Pagination Structure**: How to navigate through multiple pages

## 📊 Example: Crawling Job Listings

Here's how you would set up monitoring for a job board:

1. **Create Agency**: "Tech Jobs Board"
2. **Create Page**: "Software Engineer Listings"
3. **Define Structure**: 
   - News Links: `a.job-listing-link`
   - Title: `h2.job-title`
   - Company: `span.company-name`
   - Location: `span.job-location`

## 🔧 Configuration

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost/db

# Email (for notifications)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Selenium Grid
SELENIUM_HUB_URL=http://selenium-hub:4444/wd/hub

# Redis (for Celery)
REDIS_URL=redis://redis:6379/0
```

### Key Features

#### 🔍 Multi-Browser Support
- Uses Selenium Grid for parallel browser sessions
- Supports Chrome, Firefox, Safari
- Handles JavaScript-heavy websites

#### 📧 Notification System
- Email notifications for new content
- Telegram bot integration
- Customizable message templates

#### 🛡️ Proxy Support
- Rotate proxies to avoid rate limiting
- Configure per-agency proxy settings
- Automatic proxy health checking

#### 📈 Monitoring & Logging
- Comprehensive logging in Django admin
- Performance metrics and crawl statistics
- Error tracking and alerting

#### ⏰ Scheduling
- Flexible scheduling with cron-like syntax
- Off-time configuration to avoid peak hours
- Per-page scheduling options

## 👥 Guest Access

Want to see the framework in action? Use our guest account to explore the admin panel and see real-world examples:

- **URL**: [https://crawler.m-gh.com/secret-admin/](https://crawler.m-gh.com/secret-admin/)
- **Username**: `guest`
- **Password**: `RPxzsoen4O`

The guest account provides read-only access to see how various websites are configured and how the framework handles different types of content.

## 📱 Telegram Channels

See the framework in action through these Telegram channels that are powered by this crawler:

- [The New Yorker Agency News](https://t.me/newyorkercom)
- [Product Hunt Daily](https://t.me/producthuntdaily)
- [Python Jobs](https://t.me/iran_careers)
- [More channels...]

## 🛠️ Management Commands

Use the provided shell script for easy management:

```bash
# Start the application
./mng-api.sh start

# Stop the application
./mng-api.sh stop

# View logs
./mng-api.sh logs

# Restart services
./mng-api.sh restart
```

## 📁 Project Structure

```
crawler/
├── agency/                 # Main crawling app
│   ├── models.py          # Agency, Page, Structure models
│   ├── views.py           # API endpoints
│   ├── tasks.py           # Celery tasks
│   └── crawler_engine.py  # Core crawling logic
├── notification/           # Notification system
├── reusable/              # Shared utilities
├── crawler/               # Django settings
└── manage.py              # Django management
```

## 🔄 Development

### Running Tests
```bash
docker-compose exec web python manage.py test
```

### Code Formatting
```bash
# Format Python code
make format-python

# Lint Python code
make lint-python
```

## Maintenance

Regenerate `requirements.txt` from `requirements.in` using pip-tools in a one-off container:

```bash
cd /path/to/crawler
docker run --rm \
  -v "$(pwd):/app" \
  -w /app \
  python:3.12-slim \
  bash -c "
    apt-get update &&
    apt-get install -y --no-install-recommends libpq-dev gcc &&
    pip install pip-tools &&
    pip-compile requirements.in -o requirements.txt
  "
```

**Built with ❤️ using Django, Celery, Selenium, and Docker**
