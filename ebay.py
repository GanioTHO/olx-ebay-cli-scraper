import requests
from datetime import datetime, timezone
import json
import webbrowser
from urllib.parse import unquote
import os

class EbayScraper:
    def __init__(self, search_title, limit=None, min_price="", max_price="", offer_type="f", output_file=None, pre_auth_check=False):
        self.search_title = search_title
        self.limit = limit
        self.min_price = min_price.strip()
        self.max_price = max_price.strip()
        self.offer_type = offer_type.lower()
        self.output_file = output_file or "output_ebay.txt"

        if self.offer_type == 'a':
            self.offer_type = "AUCTION"
        else:
            self.offer_type = "FIXED_PRICE"

        if pre_auth_check:
            self.access_token = self.load_access_token()
        else:
            self.access_token = None

    def authentication(self, file_path="tokens.json"):
        import base64
        client_id = os.environ.get("PROD_EBAY_APP_ID")
        client_secret = os.environ.get("PROD_EBAY_CERT_ID")
        redirect_uri = os.environ.get("PROD_EBAY_RUNAME")
        scope = "https://api.ebay.com/oauth/api_scope"

        if not all([client_id, client_secret, redirect_uri]):
            raise EnvironmentError("Missing one or more eBay API credentials in environment variables.")

        auth_url = (
            "https://auth.ebay.com/oauth2/authorize?"
            f"client_id={client_id}&"
            "response_type=code&"
            f"redirect_uri={redirect_uri}&"
            f"scope={scope}"
        )

        webbrowser.open(auth_url)
        print("----------------------------------------------------------------------------------------------------------")
        print("WARNING! MAKE SURE TO COPY URL AFTER LOGGING IN. WEBSITE WILL TELL YOU TO CLOSE BROWSER TAB. DON'T DO IT!")
        print("----------------------------------------------------------------------------------------------------------")
        print("The OAuth signup page has been opened in your default web browser.")

        def get_auth_code():
            input("After completing the OAuth process, press Enter to continue...")
            full_url = input("Paste the full redirect URL you were redirected to here: ").strip()
            if "code=" in full_url:
                return unquote(full_url.split("code=")[1].split("&")[0])
            return unquote(full_url)

        def fetch_tokens(auth_code):
            token_url = "https://api.ebay.com/identity/v1/oauth2/token"
            auth_string = f"{client_id}:{client_secret}"
            auth_base64 = base64.b64encode(auth_string.encode("utf-8")).decode("utf-8")

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {auth_base64}",
            }

            data = {
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": redirect_uri,
            }

            return requests.post(token_url, headers=headers, data=data).json()

        def save_tokens(tokens, file_path="tokens.json"):
            with open(file_path, "w") as file:
                json.dump(tokens, file, indent=4)
            print(f"Tokens successfully saved to {file_path}. You can use the app for 1.5 years.")

        auth_code = get_auth_code()
        if auth_code:
            print("Authorization code received! Proceeding...")
            tokens = fetch_tokens(auth_code)
            if "access_token" in tokens:
                save_tokens(tokens)
        else:
            print("No authorization code provided.")

    def load_access_token(self, file_path="tokens.json"):
        try:
            with open(file_path, "r") as file:
                tokens = json.load(file)
                return tokens["access_token"]
        except (FileNotFoundError, json.decoder.JSONDecodeError):
            print("No valid tokens found. Launching authorization flow...")
            self.authentication()
            return self.load_access_token(file_path)

    def run(self):
        if not self.access_token:
            self.access_token = self.load_access_token()
        search_url = "https://api.ebay.com/buy/browse/v1/item_summary/search"

        price_filter = ""
        if self.min_price and self.max_price:
            price_filter = f"price:[{self.min_price}..{self.max_price}]"
        elif self.min_price:
            price_filter = f"price:[{self.min_price}..]"
        elif self.max_price:
            price_filter = f"price:[..{self.max_price}]"

        filters = [f"buyingOptions:{{{self.offer_type}}}"]
        if price_filter:
            filters.append(price_filter)
        filter_string = ",".join(filters)

        params = {
            "q": self.search_title,
            "filter": filter_string
        }
        if self.limit is not None:
            params["limit"] = str(self.limit)

        headers_search = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        resp_search = requests.get(search_url, headers=headers_search, params=params)
        resp_search.raise_for_status()
        data = resp_search.json()

        results = []
        for item in data.get('itemSummaries', []):
            item_data = {
                "title": item['title'],
                "url": item.get('itemWebUrl', 'No link D:')
            }
            if self.offer_type == "FIXED_PRICE":
                item_data["price"] = {
                    "value": item['price']['value'],
                    "currency": item['price']['currency']
                }
            elif self.offer_type == "AUCTION":
                item_data["current_bid_price"] = {
                    "value": item['currentBidPrice']['value'],
                    "currency": item['currentBidPrice']['currency']
                }
                end_str = item['itemEndDate']
                end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                until_end = end - now
                item_data["bid_ends_in"] = str(until_end)[:-7]
            results.append(item_data)

        lines = []
        for item in results:
            if self.offer_type == "FIXED_PRICE":
                price_val = item["price"]["value"]
                price_cur = item["price"]["currency"]
            elif self.offer_type == "AUCTION":
                price_val = item["current_bid_price"]["value"]
                price_cur = item["current_bid_price"]["currency"]
            else:
                price_val = "N/A"
                price_cur = ""

            price_str = f"{price_val} {price_cur}"
            line = f"{price_str} | {item['title']} | {item['url']}"
            lines.append(line)

        output_dir = os.path.join("Output", "EBAY")
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, self.output_file)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"Saved eBay offers to {output_path}")
