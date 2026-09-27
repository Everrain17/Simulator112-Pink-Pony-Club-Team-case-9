import json
import re
from pathlib import Path
from collections import Counter, defaultdict
import pandas as pd
EXCEL_PATH = "Классификатор_происшествий_v_046_11_ДТУ_15_11_2024_искл_пожар_задымление.xlsx"
OUTPUT_PATH = "incident-classifier.json"
REPORT_PATH = "incident-classifier-report.json"
MIN_SCENARIO_LENGTH = 20
INCIDENT_TYPES = [
    "Service101",
    "Service102",
    "Service103",
    "Service104",
    "CityInfrastructureAccident",
    "TransportObjectAccident",
    "HydraulicStructureAccident",
    "HazardousProductionAccident",
    "ServiceThanks",
    "UAV",
    "Explosion",
    "RoadObstruction",
    "TrafficAccident",
    "ComplaintAboutServices",
    "Animals",
    "Consultation",
    "Collapse",
    "AssistanceToServices",
    "NaturalDisaster",
    "OtherIncident",
    "Radiation",
    "BrokenThermometer",
    "ChildInDanger",
    "WaterAccumulation",
    "FatalOutcome",
    "SocialAssistance",
    "Training",
    "ExplosionOrTerroristThreat",
    "HazardousSubstanceOrRadiationThreat",
    "CollapseThreat",
    "PersonInDanger",
    "EnvironmentalIncident"
]
assert len(INCIDENT_TYPES) == 32
assert len(set(INCIDENT_TYPES)) == 32
DISPLAY_NAMES = {
    "Service101": "101",
    "Service102": "102",
    "Service103": "103",
    "Service104": "104",
    "CityInfrastructureAccident": "Аварии и происшествия в городском хозяйстве",
    "TransportObjectAccident": "Аварии и происшествия на транспортных объектах",
    "HydraulicStructureAccident": "Аварии на гидротехнических сооружениях",
    "HazardousProductionAccident": "Аварии на опасных и производственных объектах",
    "ServiceThanks": "Благодарность службам",
    "UAV": "БПЛА",
    "Explosion": "Взрыв",
    "RoadObstruction": "Дорожные помехи",
    "TrafficAccident": "ДТП",
    "ComplaintAboutServices": "Жалоба на действие или бездействие служб",
    "Animals": "Животные",
    "Consultation": "Консультация",
    "Collapse": "Обрушение",
    "AssistanceToServices": "Помощь службам",
    "NaturalDisaster": "Природная стихия",
    "OtherIncident": "Прочие происшествия",
    "Radiation": "Радиация",
    "BrokenThermometer": "Разбитый градусник",
    "ChildInDanger": "Ребенок в опасности",
    "WaterAccumulation": "Скопление воды",
    "FatalOutcome": "Смертельный исход",
    "SocialAssistance": "Социальная помощь",
    "Training": "Тренировка",
    "ExplosionOrTerroristThreat": "Угроза взрыва/террористического акта",
    "HazardousSubstanceOrRadiationThreat": "Угроза выброса опасных веществ и радиации",
    "CollapseThreat": "Угроза обрушения",
    "PersonInDanger": "Человек в опасности",
    "EnvironmentalIncident": "Экологическое происшествие"
}

GROUP_TO_INCIDENT_TYPE = {
    "Пожары и задымления": "Service101",
    "пожар на улице": "Service101",
    "горит транспорт": "Service101",
    "пожар в метро": "Service101",
    "пожар в МЦК": "Service101",
    "пожар в жилом доме": "Service101",
    "пожар-опасный объект": "Service101",
    "ДТП": "TrafficAccident",
    "Дорожно-транспортные происшествия без пострадавших": "TrafficAccident",
    "Дорожно-транспортные происшествия без пострадавших с опасным грузом": "TrafficAccident",
    "Дорожно-транспортные происшествия с пострадавшими": "TrafficAccident",
    "Дорожно-транспортные происшествия с пострадавшими с опасным грузом": "TrafficAccident",
    "Взрывы": "Explosion",
    "Взрыв": "Explosion",
    "Взрыв транспорт": "Explosion",
    "Угрозы взрывов и террористических актов": "ExplosionOrTerroristThreat",
    "Обрушения": "Collapse",
    "Угрозы обрушений": "CollapseThreat",
    "Опасные геологические, гидрологические и метеорологические явления": "NaturalDisaster",
    "Природная стихия": "NaturalDisaster",
    "Скопление воды Подтопление Паводок": "WaterAccumulation",
    "Экологические происшествия": "EnvironmentalIncident",
    "Нарушение экологии  в акваториях и на берегах водоемов": "EnvironmentalIncident",
    "Экологические правонарушения": "EnvironmentalIncident",
    "Аварии на гидротехнических сооружениях": "HydraulicStructureAccident",
    "Аварии на опасных и производственных объектах": "HazardousProductionAccident",
    "Авария - опасный и производственный объект": "HazardousProductionAccident",
    "Радиация": "Radiation",
    "Угрозы выброса опасных веществ": "HazardousSubstanceOrRadiationThreat",
    "Неизвестный неприятный запах": "HazardousSubstanceOrRadiationThreat",
    "Обнаружение опасных веществ / объектов": "HazardousSubstanceOrRadiationThreat",
    "Опасный груз": "HazardousSubstanceOrRadiationThreat",
    "Ртуть - обнаружение": "BrokenThermometer",
    "Разлитие горючих веществ": "HazardousSubstanceOrRadiationThreat",
    "Аварии и происшествия на транспортных объектах": "TransportObjectAccident",
    "Аварии на  объектах воздушного транспорта": "TransportObjectAccident",
    "Аварии на объектах водного транспорта": "TransportObjectAccident",
    "Аварии  на объектах железнодорожного транспорта": "TransportObjectAccident",
    "Аварии на объектах метрополитена": "TransportObjectAccident",
    "Аварии на МЦК": "TransportObjectAccident",
    "Остановка движения общественного транспорта": "TransportObjectAccident",
    "Запах газа": "Service104",
    "Запах газа на улице (вне помещения)": "Service104",
    "Запах газа в помещении (в доме, в квартире)": "Service104",
    "Нарушения в работе газового оборудования": "Service104",
    "Повреждение газопровода": "Service104",
    "Аварии и происшествия в городском хозяйстве": "CityInfrastructureAccident",
    "Массовое отключение в городском хозяйстве": "CityInfrastructureAccident",
    "Аварии в городском хозяйстве - прорыв воды": "CityInfrastructureAccident",
    "Происшествия в жилищно-коммунальным  хозяйстве - локального частного характера": "CityInfrastructureAccident",
    "Качество воды, нет воды, канализация": "CityInfrastructureAccident",
    "Электрощитовая": "CityInfrastructureAccident",
    "Провал грунта яма": "CityInfrastructureAccident",
    "Колодец люк повреждение": "CityInfrastructureAccident",
    "Дерево": "CityInfrastructureAccident",
    "Предмет - падение": "CityInfrastructureAccident",
    "ЛИФТ": "CityInfrastructureAccident",
    "Провода электрические": "CityInfrastructureAccident",
    "Провода контактные": "CityInfrastructureAccident",
    "Снег грязь мусор тротуарная плитка": "CityInfrastructureAccident",
    "повреждение элементов набережной, моста, эстакады, инженерного сооружения": "CityInfrastructureAccident",
    "Нарушение правопорядка": "Service102",
    "Автомашина - Нарушение правопорядка": "Service102",
    "Вскрыта /открыто": "Service102",
    "Вымогательство Мошенничество": "Service102",
    "Граждане с оружием": "Service102",
    "Кража, грабеж, разбой": "Service102",
    "Драка": "Service102",
    "Заложники": "Service102",
    "Имущественный спор, рейдерский захват": "Service102",
    "Нападение": "Service102",
    "нарушение тишины": "Service102",
    "Нарушение правил торговли": "Service102",
    "Нарушение ПДД": "Service102",
    "Обнаружение подозрительных предметов и транспортных средств": "Service102",
    "Подозрительные, посторонние граждане": "Service102",
    "Пьяный в общественном месте": "Service102",
    "Притон": "Service102",
    "Преступления в сфере экономики": "Service102",
    "Развратные действия": "Service102",
    "Скандал": "Service102",
    "Стрельба": "Service102",
    "Угон транспорта": "Service102",
    "Хулиганство": "Service102",
    "Хранение и сбыт наркотиков": "Service102",
    "Хранение оружия": "Service102",
    "Массовый беспорядок, скопление, пикет, забастовка, межнациональный": "Service102",
    "Происшествия военного характера": "Service102",
    "Проблемы на дороге": "RoadObstruction",
    "Дорожное движение помеха": "RoadObstruction",
    "Человек в опасности": "PersonInDanger",
    "Пропал найден похищен человек": "PersonInDanger",
    "Похищение человека": "PersonInDanger",
    "Падение с высоты, в люки, колодцы, на рельсы": "Service103",
    "Поездная травма": "Service103",
    "Зажало, придавило": "Service103",
    "Тонет, на льдине": "Service103",
    "Открыть дверь": "SocialAssistance",
    "Угроза убийством": "PersonInDanger",
    "Суицид / самойбийство": "Service103",
    "ранение": "Service103",
    "Ребенок в опасности": "ChildInDanger",
    "Смертельный исход человека": "FatalOutcome",
    "Труп, констатация смерти в квартире": "FatalOutcome",
    "Труп, констатация смерти на улице (в общественном месте)": "FatalOutcome",
    "Социальная помощь": "SocialAssistance",
    "Происшествия с участием животных": "Animals",
    "Животные": "Animals",
    "Оказание медицинской скорой и неотложной помощи": "Service103",
    "Прочие происшествия": "OtherIncident",
    "Благодарность службам": "ServiceThanks",
    "Жалоба на действие или бездействие служб": "ComplaintAboutServices",
    "Справочно-консультационная помощь": "Consultation",
    "Тренировки": "Training",
    "Помощь службам": "AssistanceToServices",
    "БПЛА": "UAV"
}
assert set(GROUP_TO_INCIDENT_TYPE.values()) == set(INCIDENT_TYPES)

SERVICE_MAPPING = {
    "101": "MCHS",
    "мчс": "MCHS",
    "пожар": "MCHS",
    "спас": "MCHS",
    "102": "POLICE",
    "полиция": "POLICE",
    "мвд": "POLICE",
    "ппс": "POLICE",
    "гибдд": "POLICE",
    "103": "AMBULANCE",
    "скорая": "AMBULANCE",
    "скорую": "AMBULANCE",
    "ссн": "AMBULANCE",
    "меди": "AMBULANCE",
    "цэмп": "AMBULANCE",
    "104": "GAS",
    "газ": "GAS",
    "мособлгаз": "GAS",
    "мособлгаз": "GAS",
    "антитеррор": "ANTITERROR",
    "фсб": "ANTITERROR",
    "мослифт": "MOSLIFT",
    "жкх": "DEPT_ZHKH",
    "цомж": "TSOMP",
    "мосводоканал": "MOSVODOCANAL",
    "зодд": "ZODD",
    "автодор": "AUTOROADS",
    "гормост": "GORMOST",
    "моэк": "MOEK",
    "мосэнерго": "MOESK",
    "моэск": "MOESK",
    "мгтс": "MGTS",
    "метро": "METRO",
    "мосгортранс": "MOSGORTRANS",
    "москоллектор": "MOSCOLLECTOR",
    "мосводосток": "MOSVODOSTOK",
    "депэкологии": "DEPECO",
    "экология": "DEPECO",
    "департамент социальной защиты": "DEP_TSZN",
    "соцзащ": "DEP_TSZN",
    "ржд": "RZD"
}
TAG_KEYWORDS = {
    "Fire": [
        "пожар",
        "горит",
        "горение",
        "возгорание",
        "огонь"
    ],
    "Flood": [
        "затоп",
        "подтоп",
        "паводок",
        "наводнение",
        "вода в подвале"
    ],
    "GasLeak": [
        "утечка газа",
        "запах газа",
        "газом пахнет",
        "газовая утечка"
    ],
    "ExplosionRisk": [
        "угроза взрыва",
        "опасность взрыва",
        "взрывчат",
        "взрывное устройство"
    ],
    "Collapse": [
        "обруш",
        "рухнул",
        "рухнула",
        "разрушение конструкции"
    ],
    "Violence": [
        "напад",
        "изби",
        "драка",
        "угроз",
        "ножом",
        "оружи"
    ],
    "Electrocution": [
        "ударило током",
        "поражение током",
        "электротравм",
        "оголенный провод"
    ],
    "TrafficAccident": [
        "дтп",
        "авария автомобиля",
        "столкновение машин",
        "столкнулись автомобили",
        "наезд"
    ],
    "PeopleTrapped": [
        "зажат",
        "заблокирован",
        "не может выбраться",
        "под завалами",
        "заперт"
    ],
    "Casualties": [
        "пострадав",
        "пострадал",
        "пострадали",
        "есть раненые"
    ],
    "ChildrenAtRisk": [
        "ребенок в опасности",
        "ребенок один",
        "дети в опасности",
        "ребенок заперт"
    ],
    "InfrastructureDamage": [
        "повреждено здание",
        "повреждена дорога",
        "поврежден мост",
        "повреждение инфраструктуры"
    ],
    "EvacuationNeeded": [
        "эвакуац",
        "эвакуировать",
        "нужна эвакуация"
    ],
    "Smoke": [
        "дым",
        "задымление",
        "дымит"
    ],
    "PublicBuilding": [
        "школ",
        "больниц",
        "поликлиник",
        "торговый центр",
        "общественное здание"
    ],
    "ResidentialBuilding": [
        "квартир",
        "жилом доме",
        "жилой дом",
        "подъезд",
        "многоквартир"
    ],
    "Hospital": [
        "больниц",
        "поликлиник",
        "медицинск"
    ],
    "School": [
        "школ",
        "детсад",
        "детский сад",
        "училищ"
    ],
    "Underground": [
        "метро",
        "подземн",
        "тоннел"
    ],
    "Bridge": [
        "мост",
        "эстакад"
    ],
    "Road": [
        "дорог",
        "трасс",
        "проезжей части",
        "перекрест"
    ],
    "NaturalArea": [
        "лес",
        "парк",
        "поле",
        "лесополос"
    ],
    "CriticalCondition": [
        "тяжелом состоянии",
        "критическом состоянии",
        "без сознания",
        "тяжело ранен"
    ],
    "Bleeding": [
        "кровотеч",
        "кровь не останавливается"
    ],
    "Fracture": [
        "перелом",
        "сломал руку",
        "сломала руку",
        "сломана нога"
    ],
    "MissingPerson": [
        "пропал",
        "пропала",
        "исчез",
        "исчезла",
        "пропавший человек"
    ]
}
def normalize_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).lower().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text.strip()
def contains_any(text, patterns):
    text = normalize_text(text)
    return any(pattern in text for pattern in patterns)
def combine_row_text(row):
    values = []
    for value in row:
        text = normalize_text(value)
        if text:
            values.append(text)
    return " | ".join(values)
def unique(items):
    result = []
    for item in items:
        if item and item not in result:
            result.append(item)
    return result
# ============================================================
# TAG EXTRACTION
# ============================================================
def extract_tags(text):
    text = normalize_text(text)
    tags = []
    for tag, patterns in TAG_KEYWORDS.items():
        if contains_any(text, patterns):
            tags.append(tag)
    return unique(tags)
# ============================================================
# SERVICE EXTRACTION
# ============================================================
def normalize_service(value):
    text = normalize_text(value)
    if not text:
        return None
    for key, service in SERVICE_MAPPING.items():
        if key in text:
            return service
    return None
def extract_services(row_text, main_service_raw):
    services = []
    main_service = normalize_service(main_service_raw)
    if main_service:
        services.append(main_service)
    for key, service in SERVICE_MAPPING.items():
        if key in row_text and service not in services:
            services.append(service)
    return unique(services)
# ============================================================
# REFERENCE DETECTION
# ============================================================
def detect_reference(text):
    text = normalize_text(text)
    if "справка" not in text:
        return None
    if re.search(r"\b101\b", text):
        return "Reference101"
    if re.search(r"\b102\b", text):
        return "Reference102"
    if re.search(r"\b103\b", text):
        return "Reference103"
    if re.search(r"\b104\b", text):
        return "Reference104"
    if "гибдд" in text:
        return "TrafficPoliceReference"
    if "городское хозяйство" in text or "жкх" in text:
        return "CityInfrastructureReference"
    if "мчс" in text or "экстренн" in text:
        return "EmergencyServiceReference"
    return None
def detect_service_incident(text, main_service_raw):
    text = normalize_text(text)
    main_service = normalize_text(main_service_raw)
    if "справка" in text:
        return None
    if (
        contains_any(text, [
            "пожар",
            "горит",
            "возгорание",
            "горение",
            "задымление"
        ])
        or contains_any(main_service, ["101", "мчс"])
    ):
        return "Service101"
    if (
        contains_any(text, [
            "полиция требуется",
            "вызвать полицию",
            "нужна полиция",
            "нападение",
            "драка",
            "грабеж",
            "разбой"
        ])
        or contains_any(main_service, ["102", "полиция", "мвд"])
    ):
        return "Service102"
    if (
        contains_any(text, [
            "скорая помощь",
            "нужна скорая",
            "вызвать скорую",
            "человеку плохо",
            "без сознания",
            "медицинская помощь",
            "приступ",
            "сильное кровотечение"
        ])
        or contains_any(main_service, ["103", "скорая", "цэмп"])
    ):
        return "Service103"
    if (
        contains_any(text, [
            "утечка газа",
            "запах газа",
            "пахнет газом",
            "газовая авария",
            "авария на газопроводе",
            "газопровод поврежден"
        ])
        or contains_any(main_service, ["104", "газовая служба", "газ"])
    ):
        return "Service104"
    return None
def detect_incident_type_from_group(group_value):
    group = normalize_text(group_value)

    if not group:
        raise ValueError(
            "Пустая 'Группа происшествий': "
            "невозможно определить IncidentType."
        )

    for source_group, incident_type in GROUP_TO_INCIDENT_TYPE.items():
        if normalize_text(source_group) == group:
            return incident_type

    raise ValueError(
        f"Неизвестная группа происшествий в Excel: {group_value!r}"
    )


TYPE_SERVICE_DEFAULTS = {
    "Service101": ["MCHS"],
    "Service102": ["POLICE"],
    "Service103": ["AMBULANCE"],
    "Service104": ["GAS"],
    "Reference101": ["MCHS"],
    "Reference102": ["POLICE"],
    "Reference103": ["AMBULANCE"],
    "Reference104": ["GAS"],
    "TrafficPoliceReference": ["POLICE"],
    "CityInfrastructureReference": ["DEPT_ZHKH"],
    "EmergencyServiceReference": ["MCHS"],
    "TrafficAccident": ["POLICE"],
    "Explosion": ["MCHS"],
    "ExplosionOrTerroristThreat": ["MCHS", "POLICE", "ANTITERROR"],
    "Collapse": ["MCHS"],
    "CollapseThreat": ["MCHS"],
    "UAV": ["MCHS"],
    "Radiation": ["MCHS"],
    "HazardousSubstanceOrRadiationThreat": ["MCHS"],
    "BrokenThermometer": ["MCHS"],
    "WaterAccumulation": ["MOSVODOCANAL"],
    "RoadObstruction": ["ZODD", "AUTOROADS"],
    "EnvironmentalIncident": ["DEPECO"],
    "Animals": ["MCHS"],
    "ChildInDanger": ["POLICE"],
    "PersonInDanger": ["POLICE"],
    "FatalOutcome": ["AMBULANCE", "POLICE"],
    "SocialAssistance": ["DEP_TSZN"],
    "CityInfrastructureAccident": ["DEPT_ZHKH"],
    "TransportObjectAccident": ["MCHS"],
    "HydraulicStructureAccident": ["MCHS"],
    "HazardousProductionAccident": ["MCHS"],
    "TechnicalFailure": ["MCHS"]
}
def services_from_tags(tags):
    services = []
    if "Fire" in tags or "Smoke" in tags:
        services.append("MCHS")
    if "GasLeak" in tags:
        services.append("GAS")
    if "ExplosionRisk" in tags:
        services.extend(["MCHS", "POLICE"])
    if "TrafficAccident" in tags:
        services.append("POLICE")
    if "Violence" in tags or "MissingPerson" in tags:
        services.append("POLICE")
    if "Casualties" in tags:
        services.append("AMBULANCE")
    if "CriticalCondition" in tags:
        services.append("AMBULANCE")
    if "Bleeding" in tags:
        services.append("AMBULANCE")
    if "PeopleTrapped" in tags:
        services.append("MCHS")
    if "Collapse" in tags:
        services.append("MCHS")
    if "Flood" in tags:
        services.append("MOSVODOCANAL")
    if "Electrocution" in tags:
        services.extend(["MOESK", "MCHS"])
    return unique(services)
def determine_services(incident_type, tags, extracted_services):
    services = []
    services.extend(
        TYPE_SERVICE_DEFAULTS.get(
            incident_type,
            []
        )
    )
    services.extend(
        services_from_tags(tags)
    )
    services.extend(extracted_services)
    services = unique(services)
    if not services:
        services = ["MCHS"]
    main_service = services[0]
    additional_services = services[1:]
    return main_service, additional_services
def build_scenario_description(row, incident_type):
    values = []
    for value in row:
        text = normalize_text(value)
        if (
            text
            and len(text) >= MIN_SCENARIO_LENGTH
            and text not in values
        ):
            values.append(text)
    if not values:
        return DISPLAY_NAMES.get(
            incident_type,
            "Происшествие"
        )
    values.sort(
        key=lambda x: len(x),
        reverse=True
    )
    return values[0]
def get_cell(row, index):
    if index >= len(row):
        return ""
    return row.iloc[index]
# Ожидаемая структура исходного Excel из текущего скрипта:
# 0  group_level
# 4  ekp_code
# 6  sign1
# 7  sign2
# 10 incident_name
# 12 service_code
# 13 main_service_raw
# 14:40 scenario
# ============================================================
# PROFILE CREATION
# ============================================================
def parse_excel():
    path = Path(EXCEL_PATH)

    if not path.exists():
        raise FileNotFoundError(
            f"Excel-файл не найден: {path.resolve()}"
        )

    df = pd.read_excel(
        path,
        header=None
    )

    # В Excel "Группа происшествий" оформлена объединенными ячейками.
    # Протягиваем группу вниз до следующей группы.
    df[5] = df[5].ffill()

    profiles = []
    diagnostics = []

    type_counts = Counter()
    confidence_counts = Counter()
    service_counts = Counter()
    group_counts = Counter()
    unmapped_groups = []

    for row_index in range(3, len(df)):
        row = df.iloc[row_index]

        row_text = combine_row_text(row)

        if not row_text:
            continue

        group_value = row.iloc[5]

        try:
            incident_type = detect_incident_type_from_group(
                group_value
            )
        except ValueError as exc:
            unmapped_groups.append({
                "row": row_index + 1,
                "group": str(group_value),
                "error": str(exc)
            })
            continue

        ekp_code = row.iloc[4]
        incident_name = row.iloc[10]
        main_service_raw = row.iloc[13]

        tags = extract_tags(row_text)
        extracted_services = extract_services(
            row_text,
            main_service_raw
        )

        main_service, additional_services = determine_services(
            incident_type,
            tags,
            extracted_services
        )

        profile = {
            "ekpCode": normalize_text(ekp_code),
            "name": normalize_text(incident_name) or DISPLAY_NAMES[
                incident_type
            ],
            "subgroup": normalize_text(group_value),
            "IncidentType": incident_type,
            "mainService": main_service,
            "additionalServices": additional_services,
            "criticalTags": tags,
            "scenarioDescription": build_scenario_description(
                row,
                incident_type
            )
        }

        profiles.append(profile)

        type_counts[incident_type] += 1
        confidence_counts["workbook_group"] += 1
        service_counts[main_service] += 1
        group_counts[str(group_value)] += 1

        diagnostics.append({
            "row": row_index + 1,
            "group": str(group_value),
            "ekpCode": profile["ekpCode"],
            "name": profile["name"],
            "IncidentType": incident_type,
            "displayName": DISPLAY_NAMES[incident_type],
            "confidence": "workbook_group",
            "mainService": main_service,
            "additionalServices": additional_services,
            "tags": tags
        })

    return (
        profiles,
        diagnostics,
        type_counts,
        confidence_counts,
        service_counts,
        group_counts,
        unmapped_groups
    )


def build_coverage_report(
    profiles,
    diagnostics,
    type_counts,
    confidence_counts,
    service_counts,
    group_counts,
    unmapped_groups
):
    missing_types = [
        incident_type
        for incident_type in INCIDENT_TYPES
        if type_counts.get(incident_type, 0) == 0
    ]

    group_mappings = [
        {
            "workbookGroup": group,
            "IncidentType": incident_type,
            "displayName": DISPLAY_NAMES[incident_type],
            "rows": group_counts.get(group, 0)
        }
        for group, incident_type in GROUP_TO_INCIDENT_TYPE.items()
    ]

    return {
        "source": EXCEL_PATH,
        "incidentTypeCount": len(INCIDENT_TYPES),
        "profiles": len(profiles),
        "representedIncidentTypes": len([
            x for x in INCIDENT_TYPES
            if type_counts.get(x, 0) > 0
        ]),
        "missingIncidentTypes": missing_types,
        "workbookGroupCount": len(GROUP_TO_INCIDENT_TYPE),
        "workbookGroupMappings": group_mappings,
        "unmappedGroups": unmapped_groups,
        "confidenceCounts": dict(confidence_counts),
        "serviceCounts": dict(service_counts),
        "typeCounts": dict(type_counts)
    }


def validate_profiles(profiles):
    errors = []
    for index, profile in enumerate(profiles):
        incident_type = profile.get(
            "IncidentType"
        )
        if incident_type not in INCIDENT_TYPES:
            errors.append({
                "index": index,
                "error": "INVALID_INCIDENT_TYPE",
                "value": incident_type
            })
        main_service = profile.get(
            "mainService"
        )
        if not main_service:
            errors.append({
                "index": index,
                "error": "EMPTY_MAIN_SERVICE"
            })
        if not isinstance(
            profile.get("additionalServices"),
            list
        ):
            errors.append({
                "index": index,
                "error": "INVALID_ADDITIONAL_SERVICES"
            })
        if not isinstance(
            profile.get("criticalTags"),
            list
        ):
            errors.append({
                "index": index,
                "error": "INVALID_TAGS"
            })
    return errors
def save_json(data, path):
    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )
def print_report(
    profiles,
    type_counts,
    confidence_counts,
    service_counts,
    validation_errors
):
    print()
    print("=" * 80)
    print("INCIDENT CLASSIFIER REPORT")
    print("=" * 80)
    print(
        f"Всего профилей: {len(profiles)}"
    )
    print(
        f"Типов в каноническом списке: {len(INCIDENT_TYPES)}"
    )
    represented = sum(
        1
        for incident_type in INCIDENT_TYPES
        if type_counts.get(
            incident_type,
            0
        ) > 0
    )
    print(
        f"Типов реально найдено в Excel: {represented}/51"
    )
    print()
    print("ТИПЫ:")
    print("-" * 80)
    for index, incident_type in enumerate(
        INCIDENT_TYPES,
        start=1
    ):
        count = type_counts.get(
            incident_type,
            0
        )
        status = "OK" if count > 0 else "MISSING"
        print(
            f"{index:02d}. "
            f"{status:7} "
            f"{incident_type:45} "
            f"{count:5} | "
            f"{DISPLAY_NAMES[incident_type]}"
        )
    print()
    print("ТОЧНОСТЬ ОПРЕДЕЛЕНИЯ:")
    print("-" * 80)
    for key, value in confidence_counts.items():
        print(
            f"{key:20} {value}"
        )
    print()
    print("ОСНОВНЫЕ СЛУЖБЫ:")
    print("-" * 80)
    for key, value in service_counts.most_common():
        print(
            f"{key:25} {value}"
        )
    print()
    print("ВАЛИДАЦИЯ:")
    if validation_errors:
        print(
            f"ОШИБОК: {len(validation_errors)}"
        )
    else:
        print(
            "Ошибок структуры профилей нет."
        )
    print("=" * 80)
    print()
# ============================================================
# MAIN
# ============================================================
def main():
    print(
        f"Читаю Excel: {EXCEL_PATH}"
    )

    (
        profiles,
        diagnostics,
        type_counts,
        confidence_counts,
        service_counts,
        group_counts,
        unmapped_groups
    ) = parse_excel()

    validation_errors = validate_profiles(
        profiles
    )

    report = build_coverage_report(
        profiles,
        diagnostics,
        type_counts,
        confidence_counts,
        service_counts,
        group_counts,
        unmapped_groups
    )

    if validation_errors:
        report["validationErrors"] = validation_errors

    save_json(
        profiles,
        OUTPUT_PATH
    )

    save_json(
        report,
        REPORT_PATH
    )

    mapping_report = {
        "source": EXCEL_PATH,
        "incidentTypes": [
            {
                "IncidentType": incident_type,
                "displayName": DISPLAY_NAMES[incident_type],
                "rows": type_counts.get(incident_type, 0)
            }
            for incident_type in INCIDENT_TYPES
        ],
        "workbookGroups": report["workbookGroupMappings"],
        "removedFromPreviousEnum": ["InternalCall", "ForeignLanguageCall", "AdditionalApplicantCall", "NonTargetCall", "Feedback112", "CallCancellation", "WrongNumber", "DutyTransfer", "Collection", "Reference101", "Reference102", "Reference103", "Reference104", "TrafficPoliceReference", "CityInfrastructureReference", "EmergencyServiceReference", "TestCall", "TechnicalFailure", "EmergencyNotification"],
        "unmappedGroups": unmapped_groups
    }

    save_json(
        mapping_report,
        "incident-type-book-mapping.json"
    )

    print()
    print("=" * 80)
    print("INCIDENT CLASSIFIER REPORT")
    print("=" * 80)
    print(f"Профили: {len(profiles)}")
    print(f"IncidentType: {len(INCIDENT_TYPES)}")
    print(f"Групп Excel: {len(GROUP_TO_INCIDENT_TYPE)}")
    print(f"Непривязанных групп: {len(unmapped_groups)}")
    print(f"Ошибок структуры: {len(validation_errors)}")
    print()

    for incident_type in INCIDENT_TYPES:
        print(
            f"{incident_type:45} "
            f"{type_counts.get(incident_type, 0):5} | "
            f"{DISPLAY_NAMES[incident_type]}"
        )

    print("=" * 80)

    if unmapped_groups:
        raise RuntimeError(
            "В Excel есть группы без явного сопоставления. "
            "Добавьте их в GROUP_TO_INCIDENT_TYPE."
        )

    if validation_errors:
        raise RuntimeError(
            "В incident-classifier.json найдены ошибки структуры."
        )


if __name__ == "__main__":
    main()