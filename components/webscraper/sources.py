# Optional per-site headers can be provided via a "headers" dict.
SOURCES = [
    {
        "name": "gcaptain",
        "url": "https://gcaptain.com/",
        "kind": "gcaptain",
        "headers": {"Referer": "https://gcaptain.com/"},
    },
    {
        "name": "marineinsight",
        "url": "https://www.marineinsight.com/category/shipping-news/",
        "kind": "marineinsight",
        "headers": {"Referer": "https://www.marineinsight.com/"},
    },
    {"name": "port_houston", "url": "https://porthouston.com/news/", "kind": "port"},
    {"name": "port_nynj", "url": "https://www.panynj.gov/port/en/press-releases.html", "kind": "port"},
    {"name": "port_savannah", "url": "https://gaports.com/news/", "kind": "port"},
    {"name": "port_charleston", "url": "https://scspa.com/news/", "kind": "port"},
    {"name": "jaxport", "url": "https://www.jaxport.com/news-media/news/", "kind": "port"},
    {"name": "port_of_miami", "url": "https://www.portmiami.biz/press-releases/", "kind": "port"},
    {"name": "port_of_new_orleans", "url": "https://portnola.com/newsroom/news", "kind": "port"},
    {"name": "port_of_mobile", "url": "https://www.asdd.com/Port-Updates", "kind": "port"},
    {"name": "port_tampa_bay", "url": "https://www.porttb.com/news-room/", "kind": "port"},
]
