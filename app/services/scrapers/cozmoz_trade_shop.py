import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote
import logging
from ...models.product import Product
import json
from ..openai_service import OpenAIService
import os

CLIENT_USERNAME = os.path.splitext(os.path.basename(__file__))[0]

logger = logging.getLogger(__name__)

class Scraper:

    def __init__(self):
        self.base_url = 'https://cozmoz.ir'
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        self.openai_service = OpenAIService(client_username=CLIENT_USERNAME)

    def extract_product_links(self, max_pages=100):
        product_links = {}
        for page_number in range(1, max_pages):
            url = f'{self.base_url}/shop/page/{page_number}/?count=36'
            response = requests.get(url, headers=self.headers)
            if response.status_code == 404:
                logger.info(f'read the list of products with {page_number} pages')
                break
            soup = BeautifulSoup(response.content, 'html.parser')
            logger.info(f'extracting product list page number:{page_number}')
            for product in soup.find_all('li', class_='product-col'):
                product_title = product.find('h3', class_='woocommerce-loop-product__title').text
                encoded_link = product.find('a')['href']
                decoded_link = unquote(encoded_link)
                product_links[product_title] = decoded_link
        return product_links

    def extract_description(self, soup):
        description_div = soup.find("div", id="tab-description")
        if description_div:
            description_elements = description_div.find_all(['li', 'p'])
            text = str()
            for element in description_elements:
                text += element.get_text()
                text += '\n'
            return text
        else:
            return None

    def extract_additional_information(self, soup):
        additional_info_div = soup.find("div", id="tab-additional_information")
        additional_info_dict = {}
        if additional_info_div:
            rows = additional_info_div.find_all("tr")
            for row in rows:
                key = row.find("th").get_text(strip=True) if row.find("th") else None
                value = row.find("td").get_text(strip=True) if row.find("td") else None
                if key and value:
                    additional_info_dict[key] = value
            return additional_info_dict
        else:
            logger.info("additional info not found.")
            return None

    def price_mapping(self, soup):
        prices = soup.find('p', class_='price').find_all('span', class_='woocommerce-Price-amount')
        price_list = []
        for p in prices:
            price_list.append(p.text)
        if len(price_list) > 0:
            if soup.find('table', class_='variations'):
                var_name = soup.find('table', class_='variations').find('th', class_='label').text.strip()
                vars = soup.find('table', class_='variations').find('select').find_all('option')
                variations = []
                for i in range(1, len(vars)):
                    variations.append((vars[i].text.strip() + ' ' + var_name))
                mape_price = {}
                mape_price[variations[0]] = price_list[0]
                mape_price[variations[-1]] = price_list[-1]
                return mape_price
            else:
                return price_list[0]
        else:
            return 'N/A'

    def extract_category(self,soup):
        if soup.find('span', class_='posted_in') :
            cat = soup.find('span', class_='posted_in').text.split(':')[-1].strip()
            cat = cat.split(',')
            cat = [i.strip() for i in cat]
            ignore = ["محصولات پرفروش","محصولات جدید", "پیشنهاد ویژه"]
            for i in ignore:
                if i in cat:
                    cat.remove(i)
            cat = ', '.join(cat)
            return cat
        else :
            return 'N/A'

    def scrape(self, url):
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            product_info = {
                'title': soup.find('h1', class_='page-title').text.strip() if soup.find('h1', class_='page-title') else 'N/A',
                'category': self.extract_category(soup) if self.extract_category(soup) else 'N/A',
                'tags': soup.find('span', class_='tagged_as').text.split(':')[-1].strip() if soup.find('span', class_='tagged_as') else 'N/A',
                'price': json.dumps(self.price_mapping(soup), ensure_ascii=False) if isinstance(self.price_mapping(soup), dict) else self.price_mapping(soup),
                'excerpt': soup.find('div', class_='woocommerce-product-details__short-description').text.strip() if soup.find('div', class_='woocommerce-product-details__short-description') else 'N/A',
                'sku': soup.find('span', class_='sku').text.strip() if soup.find('span', class_='sku') else 'N/A',
                'description': self.extract_description(soup) if self.extract_description(soup) else 'N/A',
                'stock_status': soup.find('div', class_='product_meta').find('span', class_='stock').text.strip() if soup.find('div', class_='product_meta').find('span', class_='stock') else 'موجود',
                'additional_info': json.dumps(self.extract_additional_information(soup), ensure_ascii=False) if self.extract_additional_information(soup) else 'N/A',
                'link': url
            }

            return product_info
        except requests.RequestException as e:
            print(f"Error fetching the webpage: {e}")
            return None
        except Exception as e:
            print(f"An error occurred: {e}")
            return None

    def scrape_products(self):
        product_links = self.extract_product_links()
        for title, link in product_links.items():
            product_info = self.scrape(link)
            if product_info:
                result = Product.create(
                    title=product_info['title'],
                    category=product_info['category'],
                    tags=product_info['tags'],
                    price=product_info['price'],
                    excerpt=product_info['excerpt'],
                    sku=product_info['sku'],
                    description=product_info['description'],
                    stock_status=product_info['stock_status'],
                    additional_info=product_info['additional_info'],
                    link=product_info['link'],
                    client_username=CLIENT_USERNAME
                )
                if result:
                    logger.info(f"Stored product {title} in the database")
                else:
                    logger.error(f"Failed to store product {title} in the database")

    def update_products(self):
        product_links = self.extract_product_links()
        existing_products = Product.get_all(client_username=CLIENT_USERNAME)
        existing_titles = [p['title'] for p in existing_products]

        for title in existing_titles:
            if existing_titles.count(title) > 1:
                # first remove file from openai if exists file_id
                file_id = Product.get_file_id(title, client_username=CLIENT_USERNAME)
                if file_id:
                    resp = self.openai_service.delete_single_file(file_id)
                    if resp:
                        logger.info(f"{title} file with the id:{file_id} has removed from openai")
                    else:
                        logger.error(f"failed to remove {title} file with the id {file_id} from openai")
                else:
                    logger.info(f"product {title} doesnt have file_id")

                Product.delete(title, client_username=CLIENT_USERNAME)
                logger.info(f"Deleted product {title} from the database")



        for title, link in product_links.items():
            product_info = self.scrape(link)
            if product_info:

                if title in existing_titles:
                    Product.update(title, {
                        'category': product_info['category'],
                        'tags': product_info['tags'],
                        'price': product_info['price'],
                        'excerpt': product_info['excerpt'],
                        'sku': product_info['sku'],
                        'description': product_info['description'],
                        'stock_status': product_info['stock_status'],
                        'additional_info': product_info['additional_info'],
                        'link': product_info['link']
                    }, client_username=CLIENT_USERNAME)


                else:
                    Product.create(
                        title=product_info['title'],
                        category=product_info['category'],
                        tags=product_info['tags'],
                        price=product_info['price'],
                        excerpt=product_info['excerpt'],
                        sku=product_info['sku'],
                        description=product_info['description'],
                        stock_status=product_info['stock_status'],
                        additional_info=product_info['additional_info'],
                        link=product_info['link'],
                        client_username=CLIENT_USERNAME
                    )

        for title in existing_titles:
            if title not in product_links.keys():
                file_id = Product.get_file_id(title, client_username=CLIENT_USERNAME)
                if file_id:
                    resp = self.openai_service.delete_single_file(file_id)
                    if resp:
                        logger.info(f"{title} file with the id:{file_id} has removed from openai")
                    else:
                        logger.error(f"failed to remove {title} file with the id {file_id} from openai")
                else:
                    logger.info(f"product {title} doesnt have file_id")
                Product.delete(title, client_username=CLIENT_USERNAME)
                logger.info(f"Removed product {title} from the database as it no longer exists on the website")


