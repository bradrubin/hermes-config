# Amazon Lookup for Price Monitoring

When establishing baselines for Amazon products in the price-watch workflow, identifiers come in two forms:
- **ASINs** (10-char alphanumeric, e.g. `B0GPYFP5QD`) — for Amazon-standard products
- **ISBNs** (10 or 13 digits) — for books, often requiring ISBN-13 lookup

## Lookup Ladder

```
1. web_extract on https://www.amazon.com/dp/{asin_or_isbn}   ← direct product page
2. web_extract on https://www.amazon.com/s?k={asin_or_isbn}  ← search results (fallback for CAPTCHA)
3. web_search with identifier + "amazon"                        ← Google-cache titles/prices
4. Open Library API for ISBNs: https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}
```

## Step-by-Step

### Step 1: Direct product page extraction

Try `web_extract` on `https://www.amazon.com/dp/{identifier}` for each item in batches of 5. Amazon returns:
- Product title
- Format/variant info
- Price (current and "was" / list price)
- Any "Best Seller" or "Amazon's Choice" badges

### Step 2: Fallback to search results (CAPTCHA blocks)

Amazon blocks direct product page access with "Click to continue shopping" CAPTCHA for some identifiers. When Step 1 fails:

Extract from search: `https://www.amazon.com/s?k={identifier}`

Search results return a list of items; the target item usually appears in the first result with its title, price, and format. Note: ISBNs may not resolve to exact ASIN matches in search — the ISBN-13 form (`978-...`) often works better than ISBN-10.

### Step 3: web_search as last resort

If both Step 1 and Step 2 fail, use `web_search(query="{identifier} amazon")` to find cached snippets. This rarely yields prices but can confirm the product title and format.

### Step 4: Open Library for ISBNs

For ISBNs only: `https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&format=json&details=true` returns titles, authors, publishers. Useful for confirming the correct product when the Amazon lookup is ambiguous.

## Common Issues

### ISBN-10 vs ISBN-13 mismatch
Amazon sometimes returns a different ISBN-13 (last digit may differ) than the ISBN-10 provided. Check both forms. The search result may show "Note: Amazon returned ISBN X — the provided ISBN Y may have a typo."

### Format variants
A single ASIN may have multiple format options (Kindle, Paperback, Hardcover, Audiobook). Record the format(s) available and their prices. The "main" format is usually the first one shown.

### Price display quirks
- Amazon may show "$X.XX" or just "$X" — normalize to decimal
- "Was $Y" or "List: $Y" is the previous/current list price, not the sale price
- "Deal" or "Coupon" pricing may differ from the displayed price
- Prime shipping is often free but check if it's required for the displayed price

### Search result parsing
Search results return multiple items. Filter by:
- Exact ASIN match in the URL (`/dp/{asin}`)
- Title containing the product name you expect
- Price matching the expected range

## Pitfalls

- **Don't assume web_extract on /dp/ always works.** Amazon's anti-bot protections are aggressive. Expect ~20-30% of lookups to require the search-page fallback.
- **Don't use browser tool for bulk lookups.** It's expensive and also hits CAPTCHA. Use web_extract first, then search, then browser only if nothing else works.
- **Don't confuse ASIN with ISBN.** ASINs are Amazon-specific; ISBNs are for books. A book has both. The `/dp/{asin}` URL uses the ASIN, not the ISBN.
- **Search results may return unrelated items.** Always verify the ASIN is in the URL of the matching result before using its price.
- **Prices change frequently.** The baseline is a snapshot in time. Record the retrieval timestamp alongside the price.
