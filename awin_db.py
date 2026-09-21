import csv
import io
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. Definiamo i dati in formato CSV come stringa pulita
csv_data = """id,sku,title,description,brand,product_type,sottocategoria,gender,age_group,color,size,material,price,sale_price,availability,condizione,merchant,image_link,merchant_deep_link
10001,NK-ESS-01,"Felpa con Cappuccio Essentials","Felpa in morbido cotone con cappuccio regolabile e tasca centrale.","Nike","Abbigliamento","Felpe","Unisex","Adulti","Blu","S, M, L, XL","Cotone 80%, Poliestere 20%",65.00,45.00,true,Nuovo,"Nike Store","https://static.nike.com/a/images/t_web_pdp_535_v2/f_auto,u_9ddf04c7-2a9a-4d76-add1-d15af8f0263d,c_scale,fl_relative,w_1.0,h_1.0,fl_layer_apply/eaa4550d-0a81-4f9d-9a1b-806d8464b9cb/M+NK+CLUB+BB+PO+HOODIE.png","https://www.nike.com/it/t/felpa-pullover-in-fleece-con-cappuccio-nike-club-uomo-3XHBj6KS/FN3859-494?nikegos=true&cp=19424851510_search_&Macro=--x-23953369121---c-----9211669-00198488919850&dplnk=member&gclsrc=aw.ds&gad_source=1&gad_campaignid=23948372055&gbraid=0AAAAADq9vlME2vnExSv4wXDPWGNuuRznS&gclid=Cj0KCQjwp9vTBhCWARIsANaUrjvKabLBAc_JNt-BrG1SyhGbIJgvS1QgMFIZUTZ4aRykMXo8LCWQYokaAgKBEALw_wcB"
10002,AD-TS-02,"T-Shirt Girocollo Slim Fit","Maglietta sportiva traspirante con logo stampato sul petto.","Adidas","Abbigliamento","Magliette","Uomo","Adulti","Bianco","XS, S, M, L","Cotone 100%",30.00,30.00,true,Nuovo,"Adidas Store","https://assets.adidas.com/images/h_2000,f_auto,q_auto,fl_lossy,c_fill,g_auto/0be22db732184ddd8c7338a0c5f5f886_9366/T-shirt_Slim_Ringer_3-Stripes_Bianco_KF0418_21_model.jpg","https://www.adidas.it/t-shirt-slim-ringer-3-stripes/KF0418.html?cm_mmc=AdieSEM_PLA_Google-_-adiSEM_EU_IT_SEA_Shopping_NA_LF_AlwaysOn_SA360_BRA_BRA_CrossCategory_NA_LowStock-NA-ROI-Italian-NA-PSPB_NA-_-Branded+Low+Stock+-+male-_-PRODUCT_GROUP&cm_mmca1=IT&cm_mmca2=&14484551718&ds_agid=129228440520&af_reengagement_window=30d&is_retargeting=true&pid=googleadwords_temp&c=adiSEM_EU_IT_SEA_Shopping_NA_LF_AlwaysOn_SA360_BRA_BRA_CrossCategory_NA_LowStock-NA-ROI-Italian-NA-PSPB_NA&af_channel=Shopping_Search&adicl_gclid=Cj0KCQjwp9vTBhCWARIsANaUrjtQgUk-rfk-PTqumW3uGAmTWyhLo1s-6KiK7U9VzWOZStZin2pXDt4aAiQcEALw_wcB&gclsrc=aw.ds&gad_source=1&gad_campaignid=14484551718&gbraid=0AAAAADwBzxor2wvlgR44aZdK-sewTJPiM&gclid=Cj0KCQjwp9vTBhCWARIsANaUrjtQgUk-rfk-PTqumW3uGAmTWyhLo1s-6KiK7U9VzWOZStZin2pXDt4aAiQcEALw_wcB"
10003,LV-JNS-03,"Jeans Slim Denim Chiaro","Jeans dal taglio moderno con leggero effetto dilavato.","Levi's","Abbigliamento","Pantaloni","Uomo","Adulti","Denim Chiaro","28, 30, 32, 34","Denim Elasticizzato",110.00,85.00,true,Nuovo,"Zalando","https://img01.ztat.net/article/spp-media-p1/06f72a69eabc46b999a95c2f505783ed/0f28d7f163774b6f8bb47dfbcf71d1d1.jpg?imwidth=1800","https://www.zalando.it/levis-511-slim-jeans-slim-fit-call-it-off-le222g086-k36.html?ssku=LE222G086-K360032030&lang=it&otid=default&wmc=SEM390_NB_GO._7120197842_23959381384_197936887815.&opc=2211&mpp=google|v1||pla-293946777986||9050643||g|c||813309819000||pla|LE222G086-K360032030|293946777986|1|&gad_source=1&gad_campaignid=23959381384&gbraid=0AAAABAZWKlOV_8tZZmCaWyhZUlcxx4LPK&gclid=Cj0KCQjwp9vTBhCWARIsANaUrjuyfRifnvKV9RR3LNk6kjSVCBGDpmJe1H0g1RD7alu4BjPWYdknLvMaAm9uEALw_wcB"
10004,NK-SH-04,"Scarpe Nike Air Force 1 Low","Scarpa ammortizzata ideale per il tempo libero e lo sport.","Nike","Scarpe","Sneakers","Uomo","Adulti","Bianco","40, 41, 42, 43, 44","Sintetico e Tessuto",120.00,99.00,true,Nuovo,"Foot Locker","https://assets.footlocker.com/is/image/FLDM/314101996404_01?fmt=webp-alpha&bfc=on&wid=500&hei=500","https://www.footlocker.it/it/product/nike-air-force-1-low-uomo-scarpe/314101996404.html"
10005,ZR-JK-05,"Giacca Bomber Impermeabile","Bomber leggero con zip frontale e tasche laterali.","Zara","Abbigliamento","Giacche","Donna","Adulti","Rosa","S, M, L","Poliestere",89.99,69.99,true,Nuovo,"Zara","https://static.zara.net/assets/public/53fd/dab6/644a4cc38dd8/8e0857298987/07024574620-p/07024574620-p.jpg?ts=1782900204326&w=1024","https://www.zara.com/it/it/giacca-bomber-zw-collection-p05247049.html?v1=555132994"
10006,PM-PNT-06,"Pantaloni della Tuta Jogger","Jogger comodi con elastico in vita e polsini alle caviglie.","Puma","Abbigliamento","Pantaloni","Unisex","Adulti","Grigio","S, M, L, XL","Cotone Felpato",50.00,35.00,true,Nuovo,"Puma Store","https://images.puma.com/image/upload/f_auto,q_auto,b_rgb:fafafa,w_750,h_750,t_white_blk_50/global/682606/03/mod01/fnd/EEA/fmt/png/Pantaloni-della-tuta-Essentials-con-logo-N.-1-da-uomo","https://eu.puma.com/it/it/pd/pantaloni-della-tuta-essentials-con-logo-n.-1-da-uomo/682606?swatch=03&utm_source=google&utm_medium=cpc&utm_campaign=PMAX_GGL_IT_IT_CM_High_SEA&gad_source=1&gad_campaignid=16393039363&gbraid=0AAAAAD4NdD852hkQIifCun8sNC6gKeppj&gclid=Cj0KCQjwp9vTBhCWARIsANaUrjuUKs10qpIy8rtY9mVLZcVZ-dH8afMw5R9boBq0g36sf5YS2pSUzmMaAlakEALw_wcB&mm_rf=mm_ced78b6c4424e53b2cc4"
10007,MG-DR-07,"Vestito Midi Floreale Estivo","Abito leggero con stampa floreale e scollo a V.","Mango","Abbigliamento","Abiti","Donna","Adulti","Multicolore","XS, S, M","Viscosa 100%",59.99,39.99,true,Nuovo,"Asos","https://images.asos-media.com/products/mango-vestito-midi-con-scollo-a-v-rosa-a-fiori/211214263-1-pink?$n_750w$&wid=750&fit=constrain","https://www.asos.com/it/mango/mango-vestito-midi-con-scollo-a-v-rosa-a-fiori/prd/211214263?affid=31314&_Cj0KCQjwp9vTBhCWARIsANaUrjvqUvrB-btgZyfQfP6aXNlHrF49o0r4qesTkDmIJK2jjubbRLWdTc8aAkYOEALw_wcB&channelref=product+search&ppcadref=21517426258||&utm_source=google&utm_medium=cpc&utm_campaign=21517426258&utm_content=&utm_term=&gad_source=1&gad_campaignid=21513530087&gbraid=0AAAAADqFjOCIoGnIuTi9p807LrRhrIlJc&gclid=Cj0KCQjwp9vTBhCWARIsANaUrjvqUvrB-btgZyfQfP6aXNlHrF49o0r4qesTkDmIJK2jjubbRLWdTc8aAkYOEALw_wcB"
10008,UA-TR-08,"Maglietta Sportiva Training","Maglia tecnica ad asciugatura rapida per allenamenti intensi.","Under Armour","Abbigliamento","Magliette","Uomo","Adulti","Nero","S, M, L, XL","Poliestere tecnico",40.00,25.00,true,Nuovo,"Under Armour","https://underarmour.scene7.com/is/image/Underarmour/V5-1326413-001_FC?rp=standard-0pad%7Cpdp&qlt=85&bgc=f0f0f0&wid=800&hei=1000&op_usm=1.75%2C0.3%2C2%2C0","https://www.underarmour.it/it-it/p/ua-tech-2.0/1326413.html?dwvar_1326413_color=001&dwvar_1326413_size=MD&dwvar_1326413_length=R&cid=PLA_OMD_IT_34680_4P6XMNM8D2__21496319440&gclsrc=aw.ds&gad_source=1&gad_campaignid=21486069321&gbraid=0AAAAADm-LWSHDfz-vzWLuRVrUM1In7KYo&gclid=Cj0KCQjwp9vTBhCWARIsANaUrjvyx-wXVdZiGR_mMHhHSS-wyRgf7uvfPJbrjNaUUpa3yuddFMvNoHAaAj58EALw_wcB&r"
10009,NE-CAP-09,"Cappellino da Baseball Logo","Cappellino con visiera curva e logo ricamato sul davanti.","New Era","Accessori","Cappelli","Unisex","Adulti","Nero","Taglia Unica","Cotone",28.00,28.00,true,Nuovo,"JD Sports","https://i8.amplience.net/i/jpl/jd_060061_a?$prod404itIT$&qlt=default&fmt=auto&w=480&h=613","https://www.jdsports.it/product/nero-new-era-mlb-new-york-yankees-snapback-trucker-cap/060061_jdsportsit/?utm_source=google&utm_medium=cpc&utm_campaign=it_shopping_all_products_(LOW)&gad_source=1&gad_campaignid=20490769324&gbraid=0AAAAAqniIJxhXBuhoUwAc3ndSnsNQZ2r2&gclid=Cj0KCQjwp9vTBhCWARIsANaUrjuwwMG5HwKI_0_oHrrlXwbSrdePg_emx-rYdMxbz3uBuV7GrONz-jgaAlyUEALw_wcB"
10010,NB-SN-10,"Sneaker Casual Retrò","Scarpa dallo stile classico ispirata ai modelli da corsa anni '90.","New Balance","Scarpe","Sneakers","Unisex","Adulti","Grigio/Bianco","39, 40, 41, 42, 43, 44","Camoscio e Mesh",95.00,75.00,true,Nuovo,"Zalando","https://img01.ztat.net/article/spp-media-p1/86eed0a4966f4000991afa0f34182ef1/77c6befbbeaf4bb0bf2d9d75687f51f4.jpg?imwidth=1800&filter=packshot","https://www.zalando.it/new-balance-u740-unisex-sneakers-basse-navy-ne215p015-b11.html?ssku=NE215P015-B110065000&lang=it&otid=default&wmc=SEM390_NB_GO._7120197842_23959381384_197936887815.&opc=2211&mpp=google|v1||pla-293946777986||9050643||g|c||813309819000||pla|NE215P015-B110065000|293946777986|1|&gad_source=1&gad_campaignid=23959381384&gbraid=0AAAABAZWKlOV_8tZZmCaWyhZUlcxx4LPK&gclid=Cj0KCQjwp9vTBhCWARIsANaUrjvkc-cXRzfInTQ0TXsBxkRmwnsb9zhgjEOOzzEAgJJ00XJicDjtpNoaAgrxEALw_wcB"
10011,HM-CRD-11,"Cardigan in Maglia Fine","Cardigan aperto con bottoni frontali e scollo a V.","H&M","Abbigliamento","Maglioni","Donna","Adulti","Beige","S, M, L","Acrilico e Lana",39.99,29.99,true,Nuovo,"H&M","https://image.hm.com/assets/hm/6a/5e/6a5ed0c4b3bf28c1181484b7ae2017681f4770f0.jpg?imwidth=2160","https://www2.hm.com/it_it/productpage.0579541215.html?utm_source=google&utm_medium=cpc&utm_campaign=&utm_term=&gad_source=1&gad_campaignid=23731703228&gbraid=0AAAAADvrmzSXiJJjvZKjhNW2zw5TLeQqV&gclid=Cj0KCQjwp9vTBhCWARIsANaUrjul_TlStdoZiXrt5xC-RFmViQq5z4XLTAZGTYFemkSs3JltW3PvygIaAh-8EALw_wcB"
10012,TNF-DW-12,"Piumino Leggero 100g","Giacchetto termico comprimibile con imbottitura leggera.","The North Face","Abbigliamento","Giacche","Uomo","Adulti","Nero","S, M, L, XL","Nylon con piuma sintetica",140.00,110.00,true,Nuovo,"The North Face","https://assets.thenorthface.eu/images/t_img/c_fill,f_auto,h_1140,e_sharpen:60,w_912/dpr_2.0/v1770145718/NF0A8D1UJK3-HERO/Mens-Classic-Down-Jacket-TNF-TNF-Black-HERO.jpg","https://www.thenorthface.com/it-it/p/uomo-211701/giacca-in-piumino-classic-da-uomo-NF0A8D1U?color=JK3&size=XL&utm_source=google&utm_medium=ppc&utm_campaign=TNF-IT-PMax-Shopping-Low-Volume-SKUs&gclsrc=aw.ds&gad_source=1&gad_campaignid=20726081277&gbraid=0AAAAADnEwu8zQl-UzYE2HEojvoSVjcO1t&gclid=Cj0KCQjwp9vTBhCWARIsANaUrjvPGt1y6R5rAGMguYF7hWfw_I_pRr_pBG_dyY25c_niAlBDpJJ0eUkaAuyzEALw_wcB"
10013,ZR-SK-13,"Gonna Plisse Midi","Gonna a pieghe dal taglio midi ed elegante.","Zara","Abbigliamento","Gonne","Donna","Adulti","Nero","XS, S, M","Poliestere",45.00,35.00,true,Nuovo,"Zara","https://static.zara.net/assets/public/db57/a049/25eb4b7eb74e/637d98b03aad/08338537800-p/08338537800-p.jpg?ts=1755167152065&w=1024","https://www.zara.com/it/it/gonna-midi-satinata-p08338537.html?v1=555526501"
10014,AD-SH-14,"Shorts Sportivi Running","Pantaloncini leggeri da corsa con slip interno integrato.","Adidas","Abbigliamento","Pantaloncini","Uomo","Adulti","Nero","S, M, L","Poliestere riciclato",35.00,22.00,true,Nuovo,"Amazon","https://m.media-amazon.com/images/I/713yXWq-8lL._AC_SX679_.jpg","https://www.amazon.it/adidas-Pantaloncini-Uomo-Own-Nero/dp/B0CKTQJ85X"
10015,HR-BP-15,"Zaino Casual Porta PC","Zaino capiente con scomparto imbottito per computer portatile.","Herschel","Accessori","Zaini","Unisex","Adulti","Verde Oliva","Taglia Unica","100% Tela rinforzata",79.00,79.00,true,Nuovo,"Zalando","https://img01.ztat.net/article/spp-media-p1/37642f54516b47d9a14dadc620461d9a/3a72600b001c4507bfa0df30145232bd.jpg?imwidth=1800&filter=packshot","https://www.zalando.it/herschel-kaslo-laptopfach-zaino-olive-green-h1554o0mj-n12.html?ssku=H1554O0MJ-N120ONE000&lang=it&otid=default"
10016,TH-SH-16,"Camicia Oxford Regular Fit","Camicia classica in cotone oxford con colletto button-down.","Tommy Hilfiger","Abbigliamento","Camicie","Uomo","Adulti","Bianco","S, M, L, XL","Cotone Oxford",89.00,65.00,true,Nuovo,"Tommy Hilfiger","https://tommy-europe.scene7.com/is/image/TommyEurope/MW0MW36238_0AA_main?wid=781&fmt=jpeg&qlt=95%2C1&op_sharpen=0&resMode=sharp2&op_usm=1.5%2C.5%2C0%2C0&iccEmbed=0&printRes=72","https://it.tommy.com/camicia-oxford-regular-fit-a-righe-ithaca-mw0mw362380aa"
10017,CH-SW-17,"Felpa Girocollo","Felpa classica con logo ricamato sul petto e sul polsino.","Champion","Abbigliamento","Felpe","Unisex","Adulti","Bianco/Nero","M, L, XL","Cotone e Poliestere",75.00,50.00,true,Nuovo,"Champion Store","https://www.championstore.com/cdn/shop/files/CHPEU_221998_WW001_Full_Crop.jpg?format=pjpg&v=1774530751&width=800","https://www.championstore.com/it-it/products/felpa-girocollo-tape-logo-in-interlock-da-uomo-bianco-221998-ww001?srsltid=AfmBOoq7Y1SoPRw1NKJOinNAuVtvRWLJkzJ2Wkzu9lpNmJdkVwFr6AQwpLY"
10018,NK-LG-18,"Leggings Fitness Elasticizzati","Leggings a vita alta contenitivi e coprenti per il fitness.","Nike","Abbigliamento","Pantaloni","Donna","Adulti","Nero","XS, S, M, L","Spandex e Nylon",45.00,35.00,true,Nuovo,"Nike Store","https://static.nike.com/a/images/t_web_pdp_535_v2/f_auto/4c6fdda6-cecd-4e86-902c-d9123cb8c10e/W+NP+DF+365+MR+CROP+TIGHT+USM.png","https://www.nike.com/it/t/leggings-a-lunghezza-ridotta-e-vita-media-nike-pro-donna-ebBtwh11/IQ0884-010?nikegos=true"
10019,MG-BL-19,"Blusa Elegante in Raso","Blusa morbida con scollo arricciato in tessuto satinato.","Mango","Abbigliamento","Camicie","Donna","Adulti","Rosa Cipria","S, M","Raso di Poliestere",49.99,39.99,true,Nuovo,"Mango","https://media.mango.com/is/image/punto/37064070-82-002?wid=640","https://shop.mango.com/it/it/p/donna/tops/feste/top-raso-pizzo/37064070/82/00?s=21&srsltid=AfmBOopH0GX3B_Mn3I8rTxnmap2rmVAM8hQ7Adkl3ZgZazY7OQL49z92_rw"
10020,LV-JK-20,"Giacca di Jeans Classica","Giacca di jeans lavaggio regular con taschini sul petto.","Levi's","Abbigliamento","Giacche","Unisex","Adulti","Blu Denim","S, M, L, XL","Denim di cotone",120.00,95.00,true,Nuovo,"Zalando","https://img01.ztat.net/article/spp-media-p1/190ba1fa6a3148708b6af496b244e525/4aa0a4b0503042228e5401306826c7f8.jpg?imwidth=1800","https://www.zalando.it/levis-the-trucker-jacket-giacca-di-jeans-colusa-20-l1o22t002-k27.html?ssku=L1O22T002-K27000S000&lang=it&otid=default"
"""
SCHEMA = """
CREATE TABLE prodotti (
    id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT,
    brand TEXT,
    product_type TEXT,
    sottocategoria TEXT,
    gender TEXT,
    age_group TEXT,
    color TEXT,
    size TEXT,
    material TEXT,
    price REAL NOT NULL CHECK (price >= 0),
    sale_price REAL CHECK (sale_price IS NULL OR sale_price >= 0),
    availability INTEGER NOT NULL CHECK (availability IN (0, 1)),
    condizione TEXT,
    merchant TEXT NOT NULL,
    image_link TEXT,
    merchant_deep_link TEXT,
    advertiser_id INTEGER,
    awin_feed_id TEXT,
    merchant_product_id TEXT,
    aw_deep_link TEXT,
    currency TEXT NOT NULL DEFAULT 'EUR',
    source TEXT NOT NULL DEFAULT 'demo',
    source_updated_at TEXT,
    imported_at TEXT
)
"""


def parse_products():
    products = []
    for row in csv.DictReader(io.StringIO(csv_data)):
        row["id"] = int(row["id"])
        row["price"] = float(row["price"])
        row["sale_price"] = (
            float(row["sale_price"]) if row["sale_price"].strip() else None
        )
        row["availability"] = int(row["availability"].strip().lower() == "true")
        products.append(row)
    return products


def build_database(db_path=None):
    db_path = db_path or os.path.join(BASE_DIR, "shop_database.db")
    products = parse_products()
    columns = list(products[0])
    placeholders = ", ".join("?" for _ in columns)
    column_names = ", ".join(columns)

    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE IF EXISTS prodotti")
        conn.execute(SCHEMA)
        conn.executemany(
            f"INSERT INTO prodotti ({column_names}) VALUES ({placeholders})",
            ([product[column] for column in columns] for product in products),
        )
        conn.execute("CREATE INDEX idx_prodotti_brand ON prodotti(brand)")
        conn.execute(
            "CREATE INDEX idx_prodotti_category "
            "ON prodotti(product_type, sottocategoria)"
        )
        conn.execute("CREATE INDEX idx_prodotti_merchant ON prodotti(merchant)")
        conn.execute(
            "CREATE UNIQUE INDEX idx_prodotti_awin_identity "
            "ON prodotti(advertiser_id, merchant_product_id)"
        )
        conn.execute(
            "CREATE INDEX idx_prodotti_source "
            "ON prodotti(source, advertiser_id, awin_feed_id)"
        )

    return len(products)


if __name__ == "__main__":
    total = build_database()
    print(f"Database SQLite aggiornato correttamente con {total} prodotti.")
