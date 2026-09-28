using System;
using System.Collections.Generic;
using System.Linq;
using SimCore.Entities;
using SimCore.Enums;

namespace AIEngine
{
    public static class AiPromptBuilder
    {
        public static AIPromptPayload BuildPrompt(
            Incident incident,
            CallerState caller,
            HiddenScenarioFacts hiddenFacts,
            string lastOperatorAction,
            List<string> suggestedTopics,
            List<Utterance> utterances,
            int totalElapsedSeconds,
            double deltaSeconds)
        {
            string tone = caller.PanicLevel switch
            {
                < 30 => "спокойный",
                < 50 => "нервный",
                < 70 => "взволнованный",
                < 85 => "панический",
                _ => "истеричный"
            };

            double speed = 1.0 + (caller.PanicLevel / 100.0);
            if (speed > 2.0)
                speed = 2.0;

            string context = incident.Severity switch
            {
                <= 4 => "Ситуация стабильная.",
                <= 6 => "Есть реальная угроза.",
                <= 8 => "Серьезная опасность.",
                _ => "КРИТИЧЕСКАЯ ОПАСНОСТЬ."
            };

            string personaPrompt = caller.Persona.GetActorPrompt();

            string scenario = !string.IsNullOrWhiteSpace(incident.ScenarioDescription)
                ? incident.ScenarioDescription
                : incident.Description;
            string dialogueHistory = "История диалога отсутствует. Это начало разговора.";

            if (utterances != null && utterances.Count > 0)
            {
                var recentUtterances = utterances
                    .TakeLast(12)
                    .ToList();

                if (recentUtterances.Count > 0)
                {
                    dialogueHistory = string.Join(
                        "\n",
                        recentUtterances.Select(x =>
                            $"{(x.Speaker == SpeakerRole.Operator ? "ОПЕРАТОР" : "ЗАЯВИТЕЛЬ")}: {x.Text}"
                        )
                    );
                }
            }

            string textPrompt = $@"Ты — заявитель, разговаривающий с оператором Службы-112.

ТВОЯ РОЛЬ:
Ты находишься внутри одного конкретного происшествия и отвечаешь оператору как обычный человек.
Ты НЕ являешься оператором, диспетчером, спасателем или рассказчиком.

ГЛАВНОЕ ПРАВИЛО:
Существует только одно происшествие — описанное ниже.
Не создавай новых событий и не изменяй существующее происшествие.
Не добавляй новых людей, травмы, адреса, причины или обстоятельства.

СЦЕНАРИЙ:
{scenario}

СКРЫТАЯ ИНФОРМАЦИЯ СЦЕНАРИЯ:
Адрес: {hiddenFacts.Address}
Пострадавший: {hiddenFacts.VictimAge}
Состояние и симптомы: {hiddenFacts.Symptoms}
Кто звонит: {hiddenFacts.WhoIsCalling}

Эти сведения являются частью сценария, но НЕ означают, что заявитель уже сообщил их оператору.
Не перечисляй эти сведения самостоятельно.
Сообщай конкретную информацию только тогда, когда оператор спрашивает о ней или когда она является естественным ответом на его вопрос.

ТВОЯ ЛИЧНОСТЬ:
{personaPrompt}

ТВОЁ СОСТОЯНИЕ:
{tone}
Уровень паники: {caller.PanicLevel}%

ИСТОРИЯ ДИАЛОГА:
{dialogueHistory}

ПОСЛЕДНЯЯ РЕПЛИКА ОПЕРАТОРА:
{lastOperatorAction}

ПРАВИЛА ДИАЛОГА:
1. Отвечай непосредственно на последнюю реплику оператора.
2. Учитывай историю диалога.
3. Не противоречь своим предыдущим репликам.
4. Не повторяй уже сообщённые сведения без причины.
5. Не сообщай скрытые факты без необходимости.
6. Не придумывай сведения, которых нет в сценарии.
7. Если не знаешь ответа, скажи, что не знаешь или не можешь уточнить.
8. Не изменяй происшествие ради продолжения разговора.
9. Говори только от лица заявителя.
10. Не описывай свои мысли или действия.
11. Одна короткая естественная реплика.
12. Обычно 3–15 слов.
13. Не используй служебный текст, XML или роли assistant/user.

ВАЖНО:
История диалога содержит уже произошедшие реплики.
Не отвечай на старые вопросы.
Ответь только на последнюю реплику оператора.

Ответь одной короткой репликой заявителя.";

            textPrompt = textPrompt
                .Replace("\r\n", "\n")
                .Replace("\r", "\n");

            return new AIPromptPayload(
                Timestamp: $"{totalElapsedSeconds}s",
                CallId: incident.Id,
                IncidentId: incident.Id,
                PanicLevel: caller.PanicLevel,
                EmotionalTone: tone,
                SpeakingRate: Math.Round(speed, 2),
                IncidentType: incident.Type.ToString(),
                ScenarioContext: context,
                Description: incident.Description,
                HasGivenAddress: caller.HasGivenAddress,
                HasGivenVictimsInfo: caller.HasGivenVictimsInfo,
                LastOperatorAction: lastOperatorAction,
                HiddenScenarioFacts: hiddenFacts,
                SuggestedTopics: suggestedTopics,
                IncidentSeverity: incident.Severity,
                IsCritical: incident.State == IncidentState.Critical,
                TextPrompt: textPrompt
            );
        }
    }
}