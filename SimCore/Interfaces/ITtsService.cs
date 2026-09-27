using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace SimCore.Interfaces
{
    public interface ITtsService
    {
        // Обычный синтез чанка текста в аудио-байты
        Task<byte[]> SynthesizeAsync(string text, CancellationToken ct = default);

        // Потоковый синтез на основе IAsyncEnumerable токенов Квен
        IAsyncEnumerable<byte[]> SynthesizeStreamingAsync(IAsyncEnumerable<string> textTokens, CancellationToken ct = default);
    }
}
