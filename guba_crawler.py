import requests
from bs4 import BeautifulSoup
import re
import time
import random
import sys

# List of common User-Agents to prevent bot detection
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
]

def parse_number(text):
    """Safely parse numbers from Guba, supporting Chinese units like '万' and abbreviations like 'k'/'w'"""
    if not text:
        return 0
    text = text.strip().lower()
    try:
        if '万' in text or 'w' in text:
            num_str = re.findall(r'[\d\.]+', text)
            if num_str:
                return int(float(num_str[0]) * 10000)
        if 'k' in text:
            num_str = re.findall(r'[\d\.]+', text)
            if num_str:
                return int(float(num_str[0]) * 1000)
        num_str = re.findall(r'\d+', text)
        if num_str:
            return int(num_str[0])
    except Exception:
        pass
    return 0

class GubaCrawler:
    def __init__(self, code="zssh000001"):
        self.code = code
        self.base_url = f"https://guba.eastmoney.com/list,{code},f_{{page}}.html"
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://guba.eastmoney.com/"
        }

    def fetch_page(self, page_num):
        """Fetch and parse a single chronological Guba listing page"""
        url = self.base_url.format(page=page_num)
        headers = self.headers.copy()
        headers["User-Agent"] = random.choice(USER_AGENTS)
        
        print(f"  [Crawler] Fetching page {page_num}: {url}...")
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                print(f"  [Crawler] Error: Received status code {response.status_code} for page {page_num}", file=sys.stderr)
                return []
            
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find all table rows with class 'listitem'
            rows = soup.find_all('tr', class_='listitem')
            posts = []
            
            for row in rows:
                # We expect 5 columns inside the row: Read, Reply, Title, Author, Update Time
                tds = row.find_all('td', recursive=False)
                if len(tds) < 5:
                    continue
                
                # Column 1: Read Count
                read_div = tds[0].find('div', class_='read')
                read_val = parse_number(read_div.text) if read_div else 0
                
                # Column 2: Reply Count
                reply_div = tds[1].find('div', class_='reply')
                reply_val = parse_number(reply_div.text) if reply_div else 0
                
                # Column 3: Title & Link
                title_div = tds[2].find('div', class_='title')
                if not title_div:
                    continue
                a_tag = title_div.find('a')
                if not a_tag:
                    continue
                
                title_text = a_tag.text.strip()
                href = a_tag.get('href', '')
                post_id = a_tag.get('data-postid', '')
                if not post_id and href:
                    # try to extract post_id from link, e.g., /news,zssh000001,1709281385.html
                    match = re.search(r'(\d+)\.html$', href)
                    if match:
                        post_id = match.group(1)
                
                # Column 4: Author
                author_div = tds[3].find('div', class_='author')
                author_text = author_div.text.strip() if author_div else ""
                
                # Column 5: Time (Update Time)
                time_div = tds[4].find('div', class_='update') or tds[4].find('div', class_='time')
                time_text = time_div.text.strip() if time_div else ""
                
                posts.append({
                    "post_id": post_id,
                    "title": title_text,
                    "read_count": read_val,
                    "reply_count": reply_val,
                    "author": author_text,
                    "time": time_text,
                    "href": href,
                    "source": "eastmoney",
                })
                
            print(f"  [Crawler] Successfully parsed {len(posts)} posts from page {page_num}.")
            return posts
            
        except Exception as e:
            print(f"  [Crawler] Exception occurred while fetching page {page_num}: {e}", file=sys.stderr)
            return []

    def crawl_multiple_pages(self, num_pages=5, max_posts=None):
        """Crawl multiple pages of Guba chronological post lists with random spacing"""
        all_posts = []
        seen_ids = set()
        
        for p in range(1, num_pages + 1):
            posts = self.fetch_page(p)
            for post in posts:
                p_id = post["post_id"]
                if p_id and p_id not in seen_ids:
                    seen_ids.add(p_id)
                    all_posts.append(post)
                elif not p_id: # fallback if no id is parsed
                    all_posts.append(post)
                if max_posts and len(all_posts) >= max_posts:
                    print(f"[Crawler] Reached max_posts={max_posts}, stopping early.")
                    print(f"[Crawler] Completed. Total unique posts collected: {len(all_posts)}")
                    return all_posts
            
            if p < num_pages:
                sleep_time = random.uniform(0.5, 1.5)
                time.sleep(sleep_time)
                
        print(f"[Crawler] Completed. Total unique posts collected: {len(all_posts)}")
        return all_posts

if __name__ == "__main__":
    crawler = GubaCrawler()
    # Crawl 1 page as a standalone test
    results = crawler.crawl_multiple_pages(1)
    if results:
        print(f"Sample Post: {results[0]}")
