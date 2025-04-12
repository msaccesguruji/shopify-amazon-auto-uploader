import streamlit as st
import os
import csv
import base64
import requests
import json
from io import BytesIO
from PIL import Image

# === CREDENTIALS ===
SHOPIFY_TOKEN = st.secrets["SHOPIFY_TOKEN"]
SHOPIFY_STORE = st.secrets["SHOPIFY_STORE"]
LWA_CLIENT_ID = st.secrets["LWA_CLIENT_ID"]
LWA_CLIENT_SECRET = st.secrets["LWA_CLIENT_SECRET"]
REFRESH_TOKEN = st.secrets["REFRESH_TOKEN"]
SELLER_ID = st.secrets["SELLER_ID"]
MARKETPLACE_ID = st.secrets["MARKETPLACE_ID"]
IMGBB_API_KEY = st.secrets["IMGBB_API_KEY"]

# === STATIC DATA ===
ACCESSORY_IMAGES = [
    "https://m.media-amazon.com/images/I/71gy1ba4WmL._AC_SX569_.jpg",
    "https://m.media-amazon.com/images/I/71DUS9nCUjL._AC_SX569_.jpg",
    "https://m.media-amazon.com/images/I/81UU9p0A4aL._AC_SX569_.jpg",
    "https://m.media-amazon.com/images/I/81qLAI2RmBL._AC_SX569_.jpg",
    "https://m.media-amazon.com/images/I/71HvcLmnGkL._AC_SX569_.jpg"
]
BULLETS = [
    "🎨 High-Quality Ink Printing",
    "🎖️ Proudly Veteran-Owned",
    "👶 Comfort and Convenience",
    "🎁 Perfect Baby Shower Gift",
    "📏 Versatile Sizing & Colors"
]
DESCRIPTION = "<p>Celebrate the arrival of your little one with a beautifully printed baby bodysuit from NOFO VIBES. Crafted for comfort and made with love!</p>"


def upload_and_create_shopify_product(uploaded_file, title_slug, title_full):
    # === Upload to ImgBB ===
    uploaded_file.seek(0)
    imgbb_url = "https://api.imgbb.com/1/upload"
    files = {
        "key": (None, IMGBB_API_KEY),
        "name": (None, title_slug),
        "image": uploaded_file
    }
    response = requests.post(imgbb_url, files=files)
    if not response.ok:
        raise Exception(f"ImgBB Upload Failed: {response.status_code} - {response.text}")
    image_url = response.json()["data"]["url"]

    # === Create Shopify Product ===
    shopify_url = f"https://{SHOPIFY_STORE}/admin/api/2023-01/products.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "product": {
            "title": title_full,
            "handle": title_slug,
            "body_html": DESCRIPTION,
            "vendor": "NOFO VIBES",
            "product_type": "Baby Bodysuit",
            "tags": "baby,funny,onesie,cute,custom",
            "images": [{"src": image_url}]
        }
    }

    r = requests.post(shopify_url, json=payload, headers=headers)
    r.raise_for_status()
    product = r.json()["product"]

    if not product.get("images"):
        raise Exception("Image upload failed — Shopify didn't return an image.")

    return image_url


def get_amazon_access_token():
    r = requests.post("https://api.amazon.com/auth/o2/token", data={
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
        "client_id": LWA_CLIENT_ID,
        "client_secret": LWA_CLIENT_SECRET
    })
    r.raise_for_status()
    return r.json()["access_token"]


def generate_amazon_json_feed(title, image_url):
    variations = [
        "Newborn White Short Sleeve", "Newborn White Long Sleeve", "Newborn Natural Short Sleeve",
        "0-3M White Short Sleeve", "0-3M White Long Sleeve", "0-3M Pink Short Sleeve", "0-3M Blue Short Sleeve",
        "3-6M White Short Sleeve", "3-6M White Long Sleeve", "3-6M Blue Short Sleeve", "3-6M Pink Short Sleeve",
        "6M Natural Short Sleeve", "6-9M White Short Sleeve", "6-9M White Long Sleeve", "6-9M Pink Short Sleeve",
        "6-9M Blue Short Sleeve", "12M White Short Sleeve", "12M White Long Sleeve", "12M Natural Short Sleeve",
        "12M Pink Short Sleeve", "12M Blue Short Sleeve", "18M White Short Sleeve", "18M White Long Sleeve",
        "18M Natural Short Sleeve", "24M White Short Sleeve", "24M White Long Sleeve", "24M Natural Short Sleeve"
    ]

    def format_variation(var):
        size, color, *sleeve = var.split()
        abbr = "SS" if "Short" in sleeve else "LS"
        return f"{title}-{size}-{color}-{abbr}".replace(" ", "")

    items = []
    for var in variations:
        sku = format_variation(var)
        item = {
            "sku": sku,
            "productType": "BABY_ONE_PIECE",
            "requirements": "LISTING",
            "attributes": {
                "brand": [{"value": "NOFO VIBES"}],
                "item_name": [{"value": f"{title} - Baby Boy Girl Clothes Bodysuit Funny Cute"}],
                "manufacturer": [{"value": "NOFO VIBES"}],
                "product_description": [{"value": DESCRIPTION}],
                "variation_theme": [{"value": "size_name"}],
                "size_name": [{"value": var}],
                "bullet_point": [{"value": b} for b in BULLETS],
                "main_image_url": [{"value": image_url}],
                "standard_price": [{"value": "21.99", "currency": "USD"}],
                "quantity": [{"value": "999"}]
            }
        }
        items.append(item)

    return json.dumps({
        "feedType": "POST_PRODUCT_DATA",
        "marketplaceIds": [MARKETPLACE_ID],
        "items": items
    }, indent=2)


def submit_amazon_json_feed(json_feed, access_token):
    doc_req = requests.post(
        "https://sellingpartnerapi-na.amazon.com/feeds/2021-06-30/documents",
        headers={
            "x-amz-access-token": access_token,
            "Content-Type": "application/json"
        },
        json={"contentType": "application/json"}
    )
    doc_req.raise_for_status()
    doc = doc_req.json()

    upload_res = requests.put(doc["url"], data=json_feed.encode("utf-8"), headers={"Content-Type": "application/json"})
    upload_res.raise_for_status()

    feed_req = requests.post(
        "https://sellingpartnerapi-na.amazon.com/feeds/2021-06-30/feeds",
        headers={
            "x-amz-access-token": access_token,
            "Content-Type": "application/json"
        },
        json={
            "feedType": "POST_PRODUCT_DATA",
            "marketplaceIds": [MARKETPLACE_ID],
            "inputFeedDocumentId": doc["feedDocumentId"]
        }
    )
    feed_req.raise_for_status()
    return feed_req.json()["feedId"]


def check_amazon_feed_status(feed_id, access_token):
    url = f"https://sellingpartnerapi-na.amazon.com/feeds/2021-06-30/feeds/{feed_id}"
    res = requests.get(url, headers={"x-amz-access-token": access_token, "Content-Type": "application/json"})
    res.raise_for_status()
    return res.json()


def download_amazon_processing_report(feed_status, access_token):
    if "resultFeedDocumentId" not in feed_status:
        return "Processing report not available yet."

    doc_id = feed_status["resultFeedDocumentId"]
    doc_req = requests.get(
        f"https://sellingpartnerapi-na.amazon.com/feeds/2021-06-30/documents/{doc_id}",
        headers={"x-amz-access-token": access_token}
    )
    doc_req.raise_for_status()
    doc_info = doc_req.json()

    report_res = requests.get(doc_info["url"])
    report_res.raise_for_status()
    return report_res.text


# === STREAMLIT UI ===
st.title("🍼 Upload PNG → Auto-List to Shopify + Amazon")

uploaded_file = st.file_uploader("Upload PNG File", type="png")
if uploaded_file:
    image_bytes = uploaded_file.read()
    uploaded_file.seek(0)
    image = Image.open(uploaded_file)

    file_stem = os.path.splitext(uploaded_file.name)[0]
    title_full = file_stem.replace("-", " ").replace("_", " ").title() + " - Baby Boy Girl Clothes Bodysuit Funny Cute"
    handle = file_stem.lower().replace(" ", "-").replace("_", "-") + "-baby-boy-girl-clothes-bodysuit-funny-cute"
    st.image(image, caption=title_full, use_container_width=True)

    if st.button("📤 Submit to Shopify + Amazon"):
        try:
            uploaded_file.seek(0)
            st.info("Uploading image and creating Shopify product...")
            cdn_url = upload_and_create_shopify_product(uploaded_file, handle, title_full)

            st.info("Generating Amazon JSON feed...")
            token = get_amazon_access_token()
            json_feed = generate_amazon_json_feed(file_stem, cdn_url)

            st.info("Submitting to Amazon...")
            feed_id = submit_amazon_json_feed(json_feed, token)
            st.success(f"✅ Amazon Feed Submitted! Feed ID: {feed_id}")

            st.info("Checking Amazon feed status...")
            feed_status = check_amazon_feed_status(feed_id, token)
            st.code(json.dumps(feed_status, indent=2))

            if feed_status.get("processingStatus") == "DONE":
                st.info("Downloading processing report...")
                report_text = download_amazon_processing_report(feed_status, token)
                st.code(report_text)
            else:
                st.warning("Feed not done processing yet. Please check again later.")
        except Exception as e:
            st.error(f"❌ Error: {e}")
