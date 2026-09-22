"""Person-name dictionaries + ru morphology endings (spec 007, US2/US3).

Gives the persons extractor its *dictionary* confidence layer and the
normalizer ru↔latin mappings used to collapse "Сергеем Ивановым" /
"Сергей Иванов" / "Sergey Ivanov" onto one canonical form.
"""

from __future__ import annotations

RU_FIRST_NAMES: list[str] = [
    "Сергей", "Александр", "Дмитрий", "Андрей", "Алексей", "Иван", "Михаил",
    "Виктор", "Николай", "Павел", "Владимир", "Олег", "Игорь", "Юрий", "Артём",
    "Максим", "Егор", "Роман", "Григорий", "Антон", "Ольга", "Анна", "Мария",
    "Елена", "Светлана", "Наталья", "Ирина", "Татьяна", "Екатерина", "Ксения",
    "Дарья", "Алиса", "Полина", "Юлия", "Вера", "Людмила", "Галина", "Виктория",
    "Евгения", "Надежда", "Анастасия", "Маргарита", "Софья", "Валентина", "Лариса",
]

EN_FIRST_NAMES: list[str] = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph",
    "Thomas", "Charles", "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth",
    "Susan", "Jessica", "Sarah", "Karen", "Nancy", "Sergey", "Sergei", "Olga",
    "Ivan", "Alex", "Maria", "Anna", "Elena", "Natalia", "Victor", "Pavel",
]

PATRONYMIC_ENDINGS: tuple[str, ...] = (
    "ович", "евич", "вна", "чна", "ична", "евичa",
)

SURNAME_ENDINGS_RU: tuple[str, ...] = (
    "ов", "ев", "ёв", "ова", "ева", "ёва", "ин", "ина", "ын", "ына", "ский",
    "ская", "цкий", "цкая", "кий", "кая", "их", "ых", "чук", "енко",
)

# Latin -> Cyrillic for common given names; used so "Sergey Ivanov" collapses
# onto the same canonical form as "Сергей Иванов". Reverse-transliteration of
# the tables below covers families ("Ivanov" -> "Иванов") deterministically.
LATIN_TO_CYRILLIC_FIRST_NAMES: dict[str, str] = {
    "Sergey": "Сергей", "Sergei": "Сергей", "Serj": "Сергей",
    "Alexander": "Александр", "Alexandr": "Александр",
    "Dmitry": "Дмитрий", "Dmitri": "Дмитрий",
    "Andrey": "Андрей", "Andrew": "Андрей",
    "Aleksey": "Алексей", "Alexey": "Алексей", "Alex": "Александр",
    "Ivan": "Иван", "Mikhail": "Михаил", "Michael": "Михаил",
    "Viktor": "Виктор", "Victor": "Виктор",
    "Nikolay": "Николай", "Nikolai": "Николай", "Pavel": "Павел",
    "Vladimir": "Владимир", "Oleg": "Олег", "Igor": "Игорь",
    "Yury": "Юрий", "Yuriy": "Юрий", "Artem": "Артём", "Artyom": "Артём",
    "Maksim": "Максим", "Egor": "Егор",
    "Roman": "Роман", "Grigory": "Григорий", "Anton": "Антон",
    "Olga": "Ольга", "Anna": "Анна", "Maria": "Мария", "Elena": "Елена",
    "Svetlana": "Светлана", "Natalia": "Наталья", "Natalya": "Наталья",
    "Irina": "Ирина", "Tatiana": "Татьяна", "Tatyana": "Татьяна",
    "Ekaterina": "Екатерина", "Ksenia": "Ксения", "Kseniya": "Ксения",
    "Daria": "Дарья", "Darya": "Дарья", "Julia": "Юлия", "Yulia": "Юлия",
    "Vera": "Вера", "Lyudmila": "Людмила", "Galina": "Галина",
    "Victoria": "Виктория", "Evgenia": "Евгения", "Nadezhda": "Надежда",
    "Anastasia": "Анастасия", "Margarita": "Маргарита", "Sofya": "Софья",
    "Valentina": "Валентина", "Larisa": "Лариса",
}

CYRILLIC_TO_LATIN_FIRST_NAMES: dict[str, str] = {
    "Сергей": "Sergey", "Александр": "Alexander", "Дмитрий": "Dmitry",
    "Андрей": "Andrey", "Алексей": "Alexey", "Иван": "Ivan",
    "Михаил": "Mikhail", "Виктор": "Victor", "Николай": "Nikolay",
    "Павел": "Pavel", "Владимир": "Vladimir", "Олег": "Oleg", "Игорь": "Igor",
    "Юрий": "Yury", "Артём": "Artyom", "Максим": "Maksim", "Егор": "Egor",
    "Роман": "Roman", "Григорий": "Grigory", "Антон": "Anton",
    "Ольга": "Olga", "Анна": "Anna", "Мария": "Maria", "Елена": "Elena",
    "Светлана": "Svetlana", "Наталья": "Natalia", "Ирина": "Irina",
    "Татьяна": "Tatiana", "Екатерина": "Ekaterina", "Ксения": "Ksenia",
    "Дарья": "Daria", "Алиса": "Alisa", "Полина": "Polina", "Юлия": "Julia",
    "Вера": "Vera", "Людмила": "Lyudmila", "Галина": "Galina",
    "Виктория": "Victoria", "Евгения": "Evgenia", "Надежда": "Nadezhda",
    "Анастасия": "Anastasia", "Маргарита": "Margarita", "Софья": "Sofya",
}


def first_name_entries() -> list[dict]:
    out: list[dict] = []
    for name in RU_FIRST_NAMES:
        out.append({"term": name, "payload": {"lang": "ru", "kind": "first_name"}})
    for name in EN_FIRST_NAMES:
        out.append({"term": name, "payload": {"lang": "en", "kind": "first_name"}})
    return out


def surname_entries() -> list[dict]:
    """Hermetic surname dictionary — fixture-relevant + common RU surnames."""
    names = [
        "Иванов", "Иванова", "Петров", "Петрова", "Сидоров", "Сидорова", "Смирнов",
        "Смирнова", "Кузнецов", "Кузнецова", "Попов", "Попова", "Васильев",
        "Васильева", "Соколов", "Соколова", "Михайлов", "Михайлова", "Новиков",
        "Новикова", "Фёдоров", "Фёдорова", "Морозов", "Морозова", "Волков",
        "Волкова", "Алексеев", "Алексеева", "Лебедев", "Лебедева", "Семёнов",
        "Семёнова", "Егоров", "Егорова", "Павлов", "Павлова", "Козлов", "Козлова",
        "Степанов", "Степанова", "Николаев", "Николаева", "Орлов", "Орлова",
        "Андреев", "Андреева", "Макаров", "Макарова", "Никитин", "Никитина",
        "Захаров", "Захарова", "Зайцев", "Зайцева",
    ]
    out: list[dict] = []
    for name in names:
        out.append({"term": name, "payload": {"lang": "ru", "kind": "surname"}})
    return out