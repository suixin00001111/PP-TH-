"""Country-specific profile generator for pure-HTTP BA protocol.

Thailand is the protocol-flow reference only. Profile identity data
(name / address / phone / optional CPF) MUST match the selected country.
"""
from __future__ import annotations

import random
import string
from typing import Sequence

from paypal.models import UserInfo, CardInfo, BillingAddress, generate_card as _gen_card
from paypal.regions import normalize_phone, normalize_region, get_region, DEFAULT_REGION


def generate_cpf() -> str:
    nums = [random.randint(0, 9) for _ in range(9)]
    s = sum((10 - i) * nums[i] for i in range(9))
    d1 = (s * 10) % 11 % 10
    nums.append(d1)
    s = sum((11 - i) * nums[i] for i in range(10))
    d2 = (s * 10) % 11 % 10
    nums.append(d2)
    return "".join(str(n) for n in nums)


# ---- name / street pools (romanized where PayPal forms expect Latin) ----
NAMES: dict[str, tuple[list[str], list[str]]] = {
    "TH": (
        ["Somchai", "Somsak", "Anan", "Nattapong", "Siriporn", "Suda", "Pimchanok", "Kanokwan", "Waranya", "Natcha", "Arthit", "Kittipong"],
        ["Srisawat", "Saetang", "Wongsa", "Boonmee", "Jaidee", "Nakhon", "Sutham", "Phong", "Chaiyo", "Rattana"],
    ),
    "JP": (
        ["Haruto", "Yuki", "Ren", "Sora", "Hina", "Sakura", "Mio", "Akari", "Takumi", "Kenji", "Yuto", "Aoi"],
        ["Sato", "Suzuki", "Tanaka", "Watanabe", "Ito", "Yamamoto", "Nakamura", "Kobayashi", "Kato", "Yoshida"],
    ),
    "KR": (
        ["Minjun", "Seojun", "Jiho", "Yuna", "Soyeon", "Hyejin", "Jisoo", "Minseo", "Donghyun", "Haeun"],
        ["Kim", "Lee", "Park", "Choi", "Jung", "Kang", "Cho", "Yoon", "Jang", "Lim"],
    ),
    "CN": (
        ["Wei", "Fang", "Jing", "Lei", "Ming", "Yan", "Hao", "Xin", "Ting", "Jun", "Li", "Na"],
        ["Wang", "Li", "Zhang", "Liu", "Chen", "Yang", "Huang", "Zhao", "Wu", "Zhou"],
    ),
    "HK": (
        ["KaMing", "WaiLam", "SiuMan", "WingSze", "ChunHei", "TszChing", "HoYin", "MeiLing"],
        ["Chan", "Wong", "Cheung", "Lau", "Ng", "Lee", "Lam", "Leung", "Ho", "Chow"],
    ),
    "TW": (
        ["Jiahao", "Yating", "Zhiming", "Shufen", "Weijun", "Meiling", "Junjie", "Xinyi"],
        ["Chen", "Lin", "Huang", "Zhang", "Li", "Wang", "Wu", "Liu", "Tsai", "Yang"],
    ),
    "BR": (
        ["Joao", "Pedro", "Lucas", "Gabriel", "Mateus", "Ana", "Maria", "Julia", "Beatriz", "Larissa"],
        ["Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Costa", "Rodrigues", "Almeida", "Nascimento"],
    ),
    "PT": (
        ["Tiago", "Diogo", "Rui", "Ines", "Marta", "Sofia", "Bruno", "Catarina"],
        ["Silva", "Santos", "Ferreira", "Pereira", "Oliveira", "Costa", "Martins", "Rodrigues"],
    ),
    "MX": (
        ["Carlos", "Miguel", "Diego", "Luis", "Sofia", "Valeria", "Camila", "Daniela", "Andres", "Jorge"],
        ["Hernandez", "Garcia", "Martinez", "Lopez", "Gonzalez", "Perez", "Sanchez", "Ramirez", "Torres", "Flores"],
    ),
    "ES": (
        ["Pablo", "Alejandro", "Hugo", "Lucia", "Martina", "Paula", "Alvaro", "Carmen"],
        ["Garcia", "Rodriguez", "Gonzalez", "Fernandez", "Lopez", "Martinez", "Sanchez", "Perez"],
    ),
    "AR": (
        ["Mateo", "Santiago", "Tomas", "Valentina", "Martina", "Catalina", "Agustin", "Julieta"],
        ["Gonzalez", "Rodriguez", "Fernandez", "Lopez", "Martinez", "Perez", "Gomez", "Diaz"],
    ),
    "CL": (
        ["Matias", "Benjamin", "Josefa", "Antonia", "Florencia", "Vicente", "Amanda", "Martin"],
        ["Gonzalez", "Munoz", "Rojas", "Diaz", "Perez", "Soto", "Contreras", "Silva"],
    ),
    "CO": (
        ["Santiago", "Sebastian", "Valentina", "Mariana", "Nicolas", "Isabella", "Samuel", "Laura"],
        ["Rodriguez", "Garcia", "Martinez", "Lopez", "Hernandez", "Gonzalez", "Perez", "Sanchez"],
    ),
    "PE": (
        ["Diego", "Sebastian", "Camila", "Valeria", "Rodrigo", "Lucia", "Andrea", "Fernando"],
        ["Quispe", "Flores", "Rojas", "Garcia", "Huaman", "Lopez", "Torres", "Vargas"],
    ),
    "US": (
        ["James", "Michael", "Emily", "Sarah", "Daniel", "Ashley", "Christopher", "Jessica", "Matthew", "Amanda"],
        ["Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Wilson", "Anderson", "Thomas"],
    ),
    "GB": (
        ["Oliver", "Harry", "Jack", "Amelia", "Olivia", "Isla", "George", "Emily", "Noah", "Poppy"],
        ["Smith", "Jones", "Taylor", "Brown", "Williams", "Wilson", "Johnson", "Davies", "Patel", "Wright"],
    ),
    "CA": (
        ["Liam", "Noah", "Emma", "Olivia", "Lucas", "Ava", "Ethan", "Sophia", "Mason", "Chloe"],
        ["Smith", "Brown", "Tremblay", "Martin", "Roy", "Gagnon", "Wilson", "Johnson", "MacDonald", "Lee"],
    ),
    "AU": (
        ["Jack", "William", "Charlotte", "Olivia", "Noah", "Mia", "Liam", "Amelia", "Oliver", "Isla"],
        ["Smith", "Jones", "Williams", "Brown", "Wilson", "Taylor", "Nguyen", "Johnson", "White", "Martin"],
    ),
    "NZ": (
        ["Oliver", "Jack", "Charlotte", "Isla", "Noah", "Amelia", "Leo", "Mia", "Lucas", "Harper"],
        ["Smith", "Wilson", "Brown", "Taylor", "Jones", "Williams", "Campbell", "Walker", "Thompson", "Anderson"],
    ),
    "IE": (
        ["Conor", "Sean", "Aoife", "Saoirse", "Cian", "Niamh", "Oisin", "Ciara"],
        ["Murphy", "Kelly", "OBrien", "Walsh", "Ryan", "Byrne", "OConnor", "Doyle"],
    ),
    "DE": (
        ["Lukas", "Leon", "Finn", "Mia", "Emma", "Hannah", "Paul", "Ben", "Lina", "Lea"],
        ["Mueller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann"],
    ),
    "AT": (
        ["Lukas", "Tobias", "Anna", "Sophie", "Maximilian", "Laura", "David", "Julia"],
        ["Gruber", "Huber", "Wagner", "Mueller", "Pichler", "Steiner", "Moser", "Mayer"],
    ),
    "CH": (
        ["Noah", "Leon", "Mia", "Emma", "Luca", "Lina", "Elias", "Sofia"],
        ["Meier", "Keller", "Schneider", "Weber", "Mueller", "Fischer", "Schmid", "Brunner"],
    ),
    "FR": (
        ["Louis", "Gabriel", "Emma", "Jade", "Raphael", "Louise", "Arthur", "Chloe", "Hugo", "Manon"],
        ["Martin", "Bernard", "Dubois", "Thomas", "Robert", "Richard", "Petit", "Durand", "Leroy", "Moreau"],
    ),
    "BE": (
        ["Noah", "Louis", "Emma", "Olivia", "Liam", "Mila", "Lucas", "Louise"],
        ["Peeters", "Janssens", "Maes", "Jacobs", "Mertens", "Willems", "Claes", "Goossens"],
    ),
    "IT": (
        ["Leonardo", "Francesco", "Sofia", "Giulia", "Alessandro", "Aurora", "Lorenzo", "Giorgia"],
        ["Rossi", "Russo", "Ferrari", "Esposito", "Bianchi", "Romano", "Colombo", "Ricci"],
    ),
    "NL": (
        ["Daan", "Sem", "Emma", "Tess", "Luuk", "Sara", "Finn", "Julia"],
        ["deJong", "Jansen", "deVries", "vanDenBerg", "vanDijk", "Bakker", "Visser", "Smit"],
    ),
    "SE": (
        ["William", "Liam", "Alice", "Maja", "Noah", "Elsa", "Hugo", "Astrid"],
        ["Andersson", "Johansson", "Karlsson", "Nilsson", "Eriksson", "Larsson", "Olsson", "Persson"],
    ),
    "NO": (
        ["Jakob", "Emil", "Emma", "Nora", "Oliver", "Sofie", "William", "Ella"],
        ["Hansen", "Johansen", "Olsen", "Larsen", "Andersen", "Pedersen", "Nilsen", "Kristiansen"],
    ),
    "DK": (
        ["William", "Noah", "Emma", "Ida", "Oscar", "Freja", "Carl", "Alma"],
        ["Nielsen", "Jensen", "Hansen", "Pedersen", "Andersen", "Christensen", "Larsen", "Sorensen"],
    ),
    "FI": (
        ["Elias", "Onni", "Aino", "Eevi", "Leo", "Helmi", "Eino", "Sofia"],
        ["Korhonen", "Virtanen", "Makinen", "Nieminen", "Koskinen", "Laine", "Jarvinen", "Lehtonen"],
    ),
    "PL": (
        ["Jakub", "Antoni", "Zuzanna", "Julia", "Jan", "Zofia", "Szymon", "Maja"],
        ["Nowak", "Kowalski", "Wisniewski", "Wojcik", "Kowalczyk", "Kaminski", "Lewandowski", "Zielinski"],
    ),
    "RU": (
        ["Alexander", "Dmitry", "Ivan", "Anna", "Maria", "Ekaterina", "Sergey", "Olga"],
        ["Ivanov", "Smirnov", "Kuznetsov", "Popov", "Sokolov", "Lebedev", "Kozlov", "Novikov"],
    ),
    "TR": (
        ["Yusuf", "Eymen", "Zeynep", "Elif", "Mira", "Asya", "Omer", "Defne"],
        ["Yilmaz", "Kaya", "Demir", "Sahin", "Celik", "Yildiz", "Yildirim", "Ozturk"],
    ),
    "IN": (
        ["Aarav", "Vihaan", "Aditya", "Ananya", "Isha", "Diya", "Rohan", "Kavya", "Arjun", "Neha"],
        ["Sharma", "Patel", "Singh", "Kumar", "Gupta", "Reddy", "Nair", "Khan", "Das", "Mehta"],
    ),
    "ID": (
        ["Budi", "Agus", "Rizky", "Putri", "Siti", "Ayu", "Andi", "Dewi", "Rina", "Fajar"],
        ["Santoso", "Wijaya", "Pratama", "Saputra", "Nugroho", "Hidayat", "Kusuma", "Sari", "Wulandari", "Gunawan"],
    ),
    "MY": (
        ["Ahmad", "Muhammad", "Aisyah", "Nurul", "Hafiz", "Siti", "Amir", "Farah"],
        ["Abdullah", "Ahmad", "Ismail", "Hassan", "Ibrahim", "Yusof", "Rahman", "Omar"],
    ),
    "VN": (
        ["Minh", "Anh", "Hung", "Linh", "Hoa", "Nam", "Trang", "Dung", "Tuan", "Mai"],
        ["Nguyen", "Tran", "Le", "Pham", "Hoang", "Huynh", "Phan", "Vu", "Vo", "Dang"],
    ),
    "PH": (
        ["Juan", "Miguel", "Jose", "Maria", "Angel", "Sofia", "Gabriel", "Andrea", "Carlo", "Bianca"],
        ["Santos", "Reyes", "Cruz", "Bautista", "Garcia", "Mendoza", "Torres", "Flores", "Gonzales", "Ramos"],
    ),
    "SG": (
        ["WeiJie", "JiaHui", "Ethan", "Chloe", "Ryan", "Aisha", "Daniel", "Nur"],
        ["Tan", "Lim", "Lee", "Ng", "Ong", "Wong", "Goh", "Chua"],
    ),
    "AE": (
        ["Omar", "Youssef", "Fatima", "Maryam", "Khalid", "Layla", "Hassan", "Noor"],
        ["AlHashimi", "AlMaktoum", "AlNahyan", "AlSuwaidi", "AlFalasi", "AlMazrouei", "Hassan", "Ali"],
    ),
    "SA": (
        ["Abdullah", "Mohammed", "Sara", "Noura", "Faisal", "Reem", "Khaled", "Lina"],
        ["AlSaud", "AlQahtani", "AlGhamdi", "AlHarbi", "AlOtaibi", "AlZahrani", "AlDossari", "AlShammari"],
    ),
    "IL": (
        ["Noam", "Uri", "Tamar", "Yael", "Eitan", "Maya", "Amit", "Shira"],
        ["Cohen", "Levy", "Mizrahi", "Peretz", "Biton", "Dahan", "Avraham", "Friedman"],
    ),
    "ZA": (
        ["Thabo", "Sipho", "Lerato", "Naledi", "Johan", "Anika", "Kagiso", "Zoe"],
        ["Dlamini", "Nkosi", "Ndlovu", "Botha", "VanDerBerg", "Mokoena", "Khumalo", "Naidoo"],
    ),
}

# Alias shared pools
for src, dsts in {
    "ES": ["CL", "CO", "PE"],  # already defined separately above where needed
}.items():
    pass

STREETS: dict[str, list[str]] = {
    "TH": ["Sukhumvit Road", "Silom Road", "Sathorn Road", "Lat Phrao Road", "Beach Road", "Ratchadaphisek Road"],
    "JP": ["Meiji-dori", "Omotesando", "Midosuji", "Chuo-dori", "Dotonbori", "Takeshita-dori"],
    "KR": ["Gangnam-daero", "Teheran-ro", "Sejong-daero", "Dongho-ro", "Olympic-ro"],
    "CN": ["Nanjing Road", "Chang'an Avenue", "Huaihai Road", "Zhongshan Road", "Renmin Road"],
    "HK": ["Nathan Road", "Queens Road Central", "Des Voeux Road", "Canton Road", "Hennessy Road"],
    "TW": ["Zhongxiao East Road", "Renai Road", "Zhongshan North Road", "Minsheng East Road"],
    "US": ["Main Street", "Oak Avenue", "Maple Drive", "Sunset Boulevard", "Broadway", "Market Street"],
    "GB": ["High Street", "Church Road", "Station Road", "Victoria Street", "King Street"],
    "CA": ["Yonge Street", "Robson Street", "Saint-Catherine Street", "Portage Avenue"],
    "AU": ["George Street", "Collins Street", "Queen Street", "Chapel Street"],
    "NZ": ["Queen Street", "Lambton Quay", "Cuba Street", "Cashel Street"],
    "IE": ["O'Connell Street", "Grafton Street", "Patrick Street", "Shop Street"],
    "BR": ["Avenida Paulista", "Rua Augusta", "Avenida Atlantica", "Rua Oscar Freire"],
    "MX": ["Avenida Reforma", "Calle Juarez", "Insurgentes Sur", "Paseo de la Reforma"],
    "ES": ["Gran Via", "Calle Mayor", "Passeig de Gracia", "Calle Alcala"],
    "AR": ["Avenida Corrientes", "Avenida Santa Fe", "Calle Florida", "Avenida 9 de Julio"],
    "CL": ["Avenida Providencia", "Avenida Libertador", "Calle Estado"],
    "CO": ["Carrera 7", "Calle 26", "Avenida El Dorado", "Carrera 15"],
    "PE": ["Avenida Arequipa", "Jiron de la Union", "Avenida Javier Prado"],
    "DE": ["Hauptstrasse", "Bahnhofstrasse", "Friedrichstrasse", "Unter den Linden"],
    "AT": ["Kaerntner Strasse", "Mariahilfer Strasse", "Getreidegasse"],
    "CH": ["Bahnhofstrasse", "Limmatquai", "Rue du Rhone"],
    "FR": ["Rue de Rivoli", "Avenue des Champs-Elysees", "Boulevard Saint-Germain", "Rue de la Paix"],
    "BE": ["Avenue Louise", "Rue Neuve", "Meir"],
    "IT": ["Via del Corso", "Via Montenapoleone", "Via Toledo", "Via Condotti"],
    "NL": ["Damrak", "Kalverstraat", "Coolsingel", "Leidsestraat"],
    "SE": ["Drottninggatan", "Sveavagen", "Kungsgatan"],
    "NO": ["Karl Johans gate", "Bogstadveien", "Aker Brygge"],
    "DK": ["Stroget", "Norrebrogade", "Vesterbrogade"],
    "FI": ["Mannerheimintie", "Aleksanterinkatu", "Esplanadi"],
    "PL": ["Nowy Swiat", "Marszalkowska", "Piotrkowska"],
    "PT": ["Avenida da Liberdade", "Rua Augusta", "Rua de Santa Catarina"],
    "RU": ["Tverskaya Street", "Arbat Street", "Nevsky Prospect"],
    "TR": ["Istiklal Caddesi", "Bagdat Caddesi", "Ataturk Bulvari"],
    "IN": ["MG Road", "Linking Road", "Connaught Place", "Park Street"],
    "ID": ["Jalan Sudirman", "Jalan Thamrin", "Jalan Malioboro", "Jalan Gatot Subroto"],
    "MY": ["Jalan Bukit Bintang", "Jalan Tun Razak", "Jalan Ampang"],
    "VN": ["Dong Khoi", "Nguyen Hue", "Hang Bai", "Le Loi"],
    "PH": ["Ayala Avenue", "EDSA", "Roxas Boulevard", "Taft Avenue"],
    "SG": ["Orchard Road", "Marina Boulevard", "Raffles Avenue", "Bugis Street"],
    "AE": ["Sheikh Zayed Road", "Al Wasl Road", "Jumeirah Beach Road"],
    "SA": ["King Fahd Road", "Tahlia Street", "Olaya Street"],
    "IL": ["Dizengoff Street", "Rothschild Boulevard", "Jaffa Road"],
    "ZA": ["Main Road", "Long Street", "Rivonia Road", "Commissioner Street"],
}

# city: state, city, district pool, postal pool
CITIES: dict[str, list[tuple[str, str, list[str], list[str]]]] = {
    "TH": [("BKK", "Bangkok", ["Pathum Wan", "Watthana", "Bang Rak", "Sathon"], ["10330", "10110", "10500", "10120"]),
           ("CNX", "Chiang Mai", ["Mueang Chiang Mai", "Hang Dong"], ["50200", "50230"]),
           ("CBI", "Chon Buri", ["Bang Lamung", "Si Racha"], ["20150", "20230"])],
    "JP": [("13", "Tokyo", ["Shibuya", "Shinjuku", "Minato"], ["1500002", "1600022", "1060032"]),
           ("27", "Osaka", ["Kita", "Chuo"], ["5300001", "5410041"]),
           ("14", "Yokohama", ["Nishi", "Naka"], ["2200011", "2310023"])],
    "KR": [("11", "Seoul", ["Gangnam", "Jongno", "Mapo"], ["04524", "03154", "04038"]),
           ("26", "Busan", ["Haeundae", "Jung"], ["48058", "48939"])],
    "CN": [("BJ", "Beijing", ["Chaoyang", "Haidian"], ["100000", "100080"]),
           ("SH", "Shanghai", ["Pudong", "Xuhui"], ["200120", "200030"])],
    "HK": [("HK", "Hong Kong", ["Central", "Tsim Sha Tsui", "Causeway Bay"], ["999077", "999077", "999077"])],
    "TW": [("TPE", "Taipei", ["Da'an", "Zhongzheng"], ["106", "100"]),
           ("KHH", "Kaohsiung", ["Cianjhen", "Zuoying"], ["806", "813"])],
    "US": [("CA", "Los Angeles", ["Downtown", "Hollywood"], ["90012", "90028"]),
           ("NY", "New York", ["Manhattan", "Brooklyn"], ["10001", "11201"]),
           ("TX", "Houston", ["Midtown", "Downtown"], ["77002", "77006"])],
    "GB": [("ENG", "London", ["Westminster", "Camden"], ["SW1A1AA", "NW1XAA"]),
           ("ENG", "Manchester", ["City Centre"], ["M11AE"]),
           ("SCT", "Edinburgh", ["Old Town"], ["EH11YZ"])],
    "CA": [("ON", "Toronto", ["Downtown"], ["M5H2N2"]), ("BC", "Vancouver", ["Downtown"], ["V6B1A1"])],
    "AU": [("NSW", "Sydney", ["CBD"], ["2000"]), ("VIC", "Melbourne", ["CBD"], ["3000"])],
    "NZ": [("AUK", "Auckland", ["CBD"], ["1010"]), ("WGN", "Wellington", ["CBD"], ["6011"])],
    "IE": [("D", "Dublin", ["City Centre"], ["D02"]), ("C", "Cork", ["City Centre"], ["T12"])],
    "BR": [("SP", "Sao Paulo", ["Bela Vista", "Pinheiros"], ["01310100", "05422000"]),
           ("RJ", "Rio de Janeiro", ["Copacabana", "Ipanema"], ["22041080", "22410003"])],
    "MX": [("CMX", "Mexico City", ["Centro", "Polanco"], ["06000", "11560"]),
           ("JAL", "Guadalajara", ["Centro"], ["44100"])],
    "ES": [("MD", "Madrid", ["Centro", "Salamanca"], ["28001", "28006"]),
           ("CT", "Barcelona", ["Eixample"], ["08008"])],
    "AR": [("C", "Buenos Aires", ["Palermo", "Recoleta"], ["1414", "1113"])],
    "CL": [("RM", "Santiago", ["Providencia", "Las Condes"], ["7500000", "7550000"])],
    "CO": [("DC", "Bogota", ["Chapinero", "Usaquen"], ["110221", "110111"])],
    "PE": [("LIM", "Lima", ["Miraflores", "San Isidro"], ["15074", "15036"])],
    "DE": [("BE", "Berlin", ["Mitte", "Charlottenburg"], ["10115", "10623"]),
           ("BY", "Munich", ["Altstadt"], ["80331"])],
    "AT": [("9", "Vienna", ["Innere Stadt"], ["1010"])],
    "CH": [("ZH", "Zurich", ["Altstadt"], ["8001"])],
    "FR": [("IDF", "Paris", ["1er", "Marais"], ["75001", "75004"]),
           ("ARA", "Lyon", ["Presquile"], ["69002"])],
    "BE": [("BRU", "Brussels", ["Centre"], ["1000"])],
    "IT": [("RM", "Rome", ["Centro"], ["00186"]), ("MI", "Milan", ["Centro"], ["20121"])],
    "NL": [("NH", "Amsterdam", ["Centrum"], ["1012"]), ("ZH", "Rotterdam", ["Centrum"], ["3011"])],
    "SE": [("AB", "Stockholm", ["Norrmalm"], ["11120"])],
    "NO": [("03", "Oslo", ["Sentrum"], ["0150"])],
    "DK": [("84", "Copenhagen", ["Indre By"], ["1050"])],
    "FI": [("18", "Helsinki", ["Keskusta"], ["00100"])],
    "PL": [("MZ", "Warsaw", ["Srodmiescie"], ["00-001"])],
    "PT": [("11", "Lisbon", ["Baixa"], ["1100-148"])],
    "RU": [("MOW", "Moscow", ["Tverskoy"], ["101000"])],
    "TR": [("34", "Istanbul", ["Besiktas", "Kadikoy"], ["34353", "34710"])],
    "IN": [("DL", "New Delhi", ["Connaught Place"], ["110001"]),
           ("MH", "Mumbai", ["Bandra"], ["400050"])],
    "ID": [("JK", "Jakarta", ["Menteng", "Sudirman"], ["10310", "10220"]),
           ("BA", "Denpasar", ["Renon"], ["80234"])],
    "MY": [("KUL", "Kuala Lumpur", ["Bukit Bintang"], ["50200"]),
           ("PNG", "George Town", ["City Centre"], ["10000"])],
    "VN": [("HN", "Hanoi", ["Hoan Kiem"], ["100000"]),
           ("SG", "Ho Chi Minh City", ["District 1"], ["700000"])],
    "PH": [("NCR", "Manila", ["Makati", "BGC"], ["1200", "1634"]),
           ("CEB", "Cebu", ["IT Park"], ["6000"])],
    "SG": [("SG", "Singapore", ["Orchard", "Marina Bay"], ["238801", "018956"])],
    "AE": [("DU", "Dubai", ["Downtown", "Jumeirah"], ["00000", "00000"])],
    "SA": [("01", "Riyadh", ["Olaya"], ["12211"])],
    "IL": [("TA", "Tel Aviv", ["Center"], ["61000"])],
    "ZA": [("GP", "Johannesburg", ["Sandton"], ["2196"]),
           ("WC", "Cape Town", ["City Bowl"], ["8001"])],
}


def _names_for(code: str) -> tuple[list[str], list[str]]:
    if code in NAMES:
        return NAMES[code]
    # regional fallbacks
    if code in {"CL", "CO", "PE"} and code not in NAMES:
        return NAMES.get(code, NAMES["ES"])
    if code in {"AT", "CH"}:
        return NAMES.get(code, NAMES["DE"])
    if code in {"BE"}:
        return NAMES.get(code, NAMES["FR"])
    return NAMES.get("US", (["Alex", "Sam"], ["Lee", "Brown"]))


def _streets_for(code: str) -> list[str]:
    return STREETS.get(code) or STREETS.get("US", ["Main Street"])


def _cities_for(code: str):
    return CITIES.get(code) or [("ST", "Capital", ["Center"], ["10000"])]


def generate_password(length: int = 12) -> str:
    upper = random.choice(string.ascii_uppercase)
    lower = random.choice(string.ascii_lowercase)
    digit = random.choice(string.digits)
    special = random.choice("!@#$%")
    rest = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(max(4, length - 4)))
    chars = list(upper + lower + digit + special + rest)
    random.shuffle(chars)
    return "".join(chars)


def generate_dob() -> str:
    year = random.randint(1981, 2003)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{day:02d}/{month:02d}/{year}"


def generate_email(first: str, last: str) -> str:
    num = random.randint(10, 9999)
    clean_first = "".join(ch for ch in first.lower() if ch.isalpha()) or "user"
    clean_last = "".join(ch for ch in last.lower() if ch.isalpha()) or "mail"
    domain = random.choice(["gmail.com", "outlook.com", "yahoo.com", "hotmail.com"])
    return f"{clean_first}.{clean_last}{num}@{domain}"


def normalize_thailand_phone(phone: str = "") -> tuple[str, str, str]:
    return normalize_phone("TH", phone)


def re_fullmatch_th(local: str) -> bool:
    return bool(local) and local[0] in "689" and local.isdigit() and len(local) == 9


def generate_address(country: str = DEFAULT_REGION) -> BillingAddress:
    code = normalize_region(country)
    state, city, districts, postals = random.choice(_cities_for(code))
    district = random.choice(districts)
    postal = random.choice(postals)
    street = random.choice(_streets_for(code))
    if code == "JP":
        house = f"{random.randint(1, 28)}-{random.randint(1, 20)}-{random.randint(1, 15)}"
    elif code in {"US", "CA", "GB", "AU", "NZ", "IE", "ZA"}:
        house = str(random.randint(10, 9999))
    else:
        house = str(random.randint(1, 999))
    return BillingAddress(
        street=street,
        house_number=house,
        district=district,
        city=city,
        state=state,
        postal_code=postal,
        country=code,
    )


def generate_user(phone: str = "", country: str = DEFAULT_REGION) -> UserInfo:
    code = normalize_region(country)
    firsts, lasts = _names_for(code)
    first = random.choice(firsts)
    last = random.choice(lasts)
    e164, local, cc = normalize_phone(code, phone)
    region = get_region(code)
    cpf = ""
    national_id = ""
    if region.send_identity_document and region.identity_type == "CPF":
        cpf = generate_cpf()
        national_id = cpf
    return UserInfo(
        first_name=first,
        last_name=last,
        email=generate_email(first, last),
        phone=e164,
        phone_local=local,
        phone_country_code=cc,
        password=generate_password(),
        dob=generate_dob(),
        national_id=national_id,
        cpf=cpf,
    )


def generate_card() -> CardInfo:
    return _gen_card()


def generate_oaipy_user(phone: str = "", country: str = DEFAULT_REGION) -> UserInfo:
    return generate_user(phone=phone, country=country)


def generate_oaipy_card() -> CardInfo:
    return generate_card()


def generate_oaipy_address(country: str = DEFAULT_REGION) -> BillingAddress:
    return generate_address(country=country)


def generate_oaipy_profile(phone: str = "", country: str = DEFAULT_REGION) -> dict:
    code = normalize_region(country)
    return {
        "user": generate_user(phone=phone, country=code),
        "card": generate_card(),
        "address": generate_address(country=code),
    }


def generate_random_email(country: str = DEFAULT_REGION) -> str:
    code = normalize_region(country)
    firsts, lasts = _names_for(code)
    return generate_email(random.choice(firsts), random.choice(lasts))
