using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using SimCore.Entities;

namespace SimCore.Interfaces
{
    public interface IAiClient
    {
        // 1. Метод синхронной генерации
        Task<string> GenerateResponseAsync(string textPrompt, string operatorReply);

        // 1.1. Метод асинхронного стриминга реплик заявителя
        IAsyncEnumerable<string> GenerateResponseStreamingAsync(string textPrompt, string operatorReply, CancellationToken ct = default);

        // 2. Метод онлайн-оценки действий оператора на линии
        Task<OperatorActionAnalysis> AnalyzeOperatorReplyAsync(string operatorReply, string incidentDescription);

        // 3. Метод финальной ИИ-проверки текста карточки
        Task<TextAnalysisResult?> AnalyzeCardTextAsync(string operatorNotes, IncidentGroundTruth groundTruth);
    }
}
