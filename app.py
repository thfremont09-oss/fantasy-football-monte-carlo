"""Monte Sports Lab: start here.  Run with:  streamlit run app.py

This wraps the Streamlit site (main.py) with extra routes on the same server: real HTML for search engines and
link previews on every page, the guides, sitemap.xml, robots.txt and the icons (see seo/site.py).
"""

import streamlit as st

from seo.site import routes

app = st.App("main.py", routes=routes())
