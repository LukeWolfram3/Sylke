# WordPress Crawler Deployment Guide for Render

## 🚀 Quick Start

Your crawlers are optimized for **uninterrupted crawling** on Render with multiple deployment options.

## 📁 Files Overview

- `start_crawlers.py` - Unified deployment script
- `render.yaml` - Render service configuration
- `Procfile` - Process definitions
- `requirements.txt` - Updated dependencies
- `render_crawler.py` - Web service for monitoring

## 🔧 Deployment Options

### Option 1: Background Worker (Recommended)

**Best for**: Long-running, uninterrupted crawling

```bash
# Deploy as background worker
git add .
git commit -m "Add Render deployment configuration"
git push origin main
```

- Navigate to [Render Dashboard](https://render.com)
- Create "Background Worker" service
- Connect your GitHub repo
- Use build command: `pip install -r requirements.txt`
- Use start command: `python start_crawlers.py`

### Option 2: Web Service with Manual Control

**Best for**: Monitoring and controlling crawlers

- Deploy as "Web Service"
- Access crawler at `https://yourapp.onrender.com`
- Start/stop crawlers via web interface
- Download results via `/download` endpoint

### Option 3: Multiple Workers

**Best for**: Running different crawlers simultaneously

Deploy both:

- Simple crawler as one worker
- Robust crawler as another worker

## 🎛️ Configuration

### Environment Variables

Set these in your Render service:

```bash
CRAWLER_MODE=simple        # Options: simple, robust, sequential
PYTHONUNBUFFERED=1        # For real-time logging
```

### Crawler Modes

- `simple` - Run simple_wp_crawler.py only
- `robust` - Run robust_wp_crawler.py only
- `sequential` - Run simple first, then robust

## 📊 Monitoring

### Logs

- View real-time logs in Render dashboard
- Download log files via web interface
- Check `crawler_deployment.log` for detailed info

### Progress Tracking

- Both crawlers resume from where they left off
- Results saved to `wordpress_idns.csv`
- Progress logged every 25 IDNs

## 🛡️ Error Handling

### Resume Capability

- ✅ Both crawlers skip already processed IDNs
- ✅ Results saved incrementally
- ✅ Automatic retry on failures

### Timeout Protection

- Conservative delays prevent rate limiting
- Robust error handling for network issues
- Graceful shutdown on interruption

## 🚦 Deployment Steps

1. **Push to GitHub**

   ```bash
   git add .
   git commit -m "Deploy WordPress crawlers to Render"
   git push origin main
   ```

2. **Create Render Service**

   - Go to [Render Dashboard](https://render.com)
   - Click "New" → "Background Worker"
   - Connect your GitHub repo
   - Branch: `main`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python start_crawlers.py`

3. **Configure Environment**

   - Add environment variable: `CRAWLER_MODE=simple`
   - Add environment variable: `PYTHONUNBUFFERED=1`

4. **Deploy**
   - Click "Create Background Worker"
   - Monitor logs for progress

## 📈 Performance Tips

### Single Worker (Recommended)

- Use `simple_wp_crawler.py` for best balance
- Processes ~3-5 IDNs per minute
- Lower chance of rate limiting

### Multiple Workers (Advanced)

- Run both crawlers on different Render services
- Ensure they don't conflict
- Monitor resource usage

## 🔍 Troubleshooting

### Common Issues

1. **Rate Limiting**

   - Increase delays in crawler configuration
   - Use single worker instead of multiple

2. **Memory Issues**

   - Render has memory limits
   - Simple crawler uses less memory

3. **Timeout Issues**
   - Background workers don't have HTTP timeouts
   - Web services timeout after 30 seconds

### Debug Steps

1. Check Render logs for error messages
2. Verify environment variables are set
3. Ensure `acuity_idns.csv` exists
4. Check `wordpress_idns.csv` for progress

## 📊 Expected Timeline

- **1,754 IDNs remaining** (as of last run)
- **~3 IDNs per minute** average rate
- **~10 hours** total estimated time
- **Resume capability** if interrupted

## 🎯 Recommendation

For **maximum reliability** and **minimal interruption**:

1. Deploy as **Background Worker**
2. Use **simple crawler mode**
3. Set `CRAWLER_MODE=simple`
4. Monitor via Render dashboard logs

This setup will crawl all remaining IDNs without interruption and automatically resume if there are any issues.

## 🔗 Useful Commands

```bash
# Check local progress
tail -f simple_crawler.log

# View results
head -20 wordpress_idns.csv

# Count processed IDNs
wc -l wordpress_idns.csv
```
