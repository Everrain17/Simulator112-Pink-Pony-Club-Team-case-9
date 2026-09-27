import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import AsyncSessionLocal, get_engine
from app.models.classifier import DialogStage, EmotionalState, InterferenceType

# IMPORTANT:
# SimCore owns IncidentType / ServiceType and the classifier profiles.
# This seed intentionally contains only Python-owned auxiliary dictionaries.

DIALOG_STAGES = [
    ("greeting", "Приветствие, представление", True, 10),
    ("problem_report", "Первичное сообщение абонента", False, 20),
    ("address_elicitation", "Выяснение адреса", True, 30),
    ("incident_clarification", "Уточнение характера происшествия", True, 40),
    ("caller_info", "Выяснение данных заявителя", False, 50),
    ("victim_info", "Выяснение наличия пострадавших", True, 60),
    ("additional_info", "Дополнительные уточнения", False, 70),
    ("instruction", "Инструктаж абонента", True, 80),
    ("service_transfer", "Передача в ДДС", True, 90),
    ("closing", "Завершение разговора", True, 100),
]

EMOTIONAL_STATES = [
    ("calm", "Спокойное", "Ровный темп, чёткая дикция"),
    ("anxious", "Тревожное", "Ускоренный темп, повторы"),
    ("panic", "Паника", "Крики, бессвязная речь, перебивания"),
    ("aggressive", "Агрессивное", "Повышенный тон, оскорбления"),
    ("confused", "Растерянное", "Замедленная речь, паузы, неполные ответы"),
    ("whisper", "Шёпот", "Тихая речь (скрытая угроза)"),
    ("child", "Ребёнок", "Детская лексика, страх"),
]

INTERFERENCE_TYPES = [
    ("none", "Помех нет"),
    ("noise", "Шум на линии"),
    ("interruption", "Прерывание связи"),
    ("echo", "Эхо"),
    ("third_party", "Посторонние голоса"),
    ("language_barrier", "Языковой барьер"),
]


async def seed_stages(db) -> int:
    created = 0
    for code, name, required, order_index in DIALOG_STAGES:
        row = await db.get(DialogStage, code)
        if row is not None:
            continue
        db.add(
            DialogStage(
                code=code,
                name=name,
                is_required=required,
                order_index=order_index,
            )
        )
        created += 1
    return created


async def seed_emotions(db) -> int:
    created = 0
    for code, name, description in EMOTIONAL_STATES:
        row = await db.get(EmotionalState, code)
        if row is not None:
            continue
        db.add(
            EmotionalState(
                code=code,
                name=name,
                description=description,
            )
        )
        created += 1
    return created


async def seed_interferences(db) -> int:
    created = 0
    for code, name in INTERFERENCE_TYPES:
        row = await db.get(InterferenceType, code)
        if row is not None:
            continue
        db.add(InterferenceType(code=code, name=name))
        created += 1
    return created


async def main() -> None:
    print("→ seeding Python-owned auxiliary dictionaries...")
    async with AsyncSessionLocal() as db:
        stages = await seed_stages(db)
        emotions = await seed_emotions(db)
        interferences = await seed_interferences(db)
        await db.commit()

        print(f"  dialog_stages: +{stages}")
        print(f"  emotional_states: +{emotions}")
        print(f"  interference_types: +{interferences}")
        print("  services / incident_types: SKIPPED (owned by SimCore)")

    await get_engine().dispose()
    print("done.")


if __name__ == "__main__":
    asyncio.run(main())
