"""Monte Sports Lab: start here.  Run with:  streamlit run app.py

This wraps the Streamlit site (main.py) with extra routes on the same server: real HTML for search engines and
link previews on every page, the guides, sitemap.xml, robots.txt and the icons (see seo/site.py).
"""

from ffmc.mem import limit_arenas, start_housekeeping

limit_arenas()                          # before anything allocates much: keeps threaded memory in check
start_housekeeping()                    # hands freed memory back to the system every few seconds

import streamlit as st                  # noqa: E402

from seo.site import routes             # noqa: E402

app = st.App("main.py", routes=routes())
