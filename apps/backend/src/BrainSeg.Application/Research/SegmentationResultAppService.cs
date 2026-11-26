using System.Linq.Expressions;
using BrainSeg.Inference;
using BrainSeg.Storage;
using Microsoft.AspNetCore.Authorization;
using Volo.Abp;
using Volo.Abp.Application.Dtos;
using Volo.Abp.Content;
using Volo.Abp.Uow;

namespace BrainSeg.Research;

[Authorize(ResearchPermissions.SegmentationResults.Default)]
public class SegmentationResultAppService(ISegmentationResultRepository results, ISegmentationJobRepository jobs,
    IBrainStudyRepository studies, IObjectStorage storage, ResearchArtifactService artifacts,
    IMlInferenceClient inferenceClient)
    : ResearchAppService, ISegmentationResultAppService
{
    private static readonly IReadOnlyDictionary<string, Expression<Func<SegmentationResult, object>>> Sorting =
        new Dictionary<string, Expression<Func<SegmentationResult, object>>>(StringComparer.OrdinalIgnoreCase)
        {
            ["creationTime"] = value => value.CreationTime,
            ["createdTime"] = value => value.CreatedTime,
            ["inferenceMilliseconds"] = value => value.InferenceMilliseconds,
            ["tumorAreaPixels"] = value => value.TumorAreaPixels
        };

    public virtual async Task<SegmentationResultDto> GetAsync(Guid id, CancellationToken cancellationToken = default) =>
        Map<SegmentationResult, SegmentationResultDto>(await results.GetAsync(id, cancellationToken: cancellationToken));

    public virtual async Task<PagedResultDto<SegmentationResultDto>> GetListAsync(SegmentationResultListInput input, CancellationToken cancellationToken = default)
    {
        var query = await results.GetQueryableAsync();
        if (input.JobId.HasValue) query = query.Where(value => value.JobId == input.JobId);
        if (!string.IsNullOrWhiteSpace(input.Filter))
        {
            var filter = input.Filter.Trim().ToLowerInvariant();
            var matchingJobs = (await jobs.GetQueryableAsync()).Where(job => job.CorrelationId.ToLower().Contains(filter)).Select(job => job.Id);
            query = query.Where(value => matchingJobs.Contains(value.JobId));
        }
        return await PageAsync<SegmentationResult, SegmentationResultDto>(query, input, Sorting, cancellationToken);
    }

    [Authorize(ResearchPermissions.SegmentationResults.Download)]
    public virtual async Task<IRemoteStreamContent> DownloadMaskAsync(Guid id,
        CancellationToken cancellationToken = default)
    {
        var result = await results.GetAsync(id, cancellationToken: cancellationToken);
        await artifacts.VerifyAsync(result.MaskObjectKey, result.MaskSha256, cancellationToken);
        var stream = await storage.OpenReadAsync(result.MaskObjectKey, cancellationToken);
        return new RemoteStreamContent(stream, "prediction.nii.gz", "application/gzip");
    }

    [Authorize(ResearchPermissions.SegmentationResults.Evaluate)]
    [UnitOfWork(isTransactional: false)]
    public virtual async Task<SegmentationResultDto> EvaluateAsync(Guid id, ResearchCommandInput input,
        CancellationToken cancellationToken = default)
    {
        var result = await results.GetAsync(id, cancellationToken: cancellationToken);
        CheckStamp(result.ConcurrencyStamp, input.ConcurrencyStamp);
        var job = await jobs.GetAsync(result.JobId, cancellationToken: cancellationToken);
        var study = await studies.GetAsync(job.StudyId, cancellationToken: cancellationToken);
        if (study.GroundTruthObjectKey is null || study.GroundTruthSha256 is null)
            throw new BusinessException(ResearchErrors.GroundTruthNotRegistered);
        if (result.RemotePredictionObjectKey is null || result.RemotePredictionSha256 is null
            || job.InputSha256 is null || job.ModelSemanticVersion is null || job.Architecture is null
            || job.PreprocessingVersion is null || job.Threshold is null)
            throw new BusinessException(ResearchErrors.ArtifactUnavailable);

        await artifacts.VerifyAsync(study.OriginalFileObjectKey, job.InputSha256, cancellationToken);
        await artifacts.VerifyAsync(study.GroundTruthObjectKey, study.GroundTruthSha256, cancellationToken);
        InferenceEvaluationResponse evaluation;
        try
        {
            evaluation = await inferenceClient.EvaluateAsync(study.OriginalFileObjectKey,
                study.GroundTruthObjectKey, result.RemotePredictionObjectKey, job.CorrelationId,
                cancellationToken);
        }
        catch (InferenceClientException exception)
        {
            var errorCode = exception.Code switch
            {
                "INVALID_LABELS" or "INVALID_NIFTI" or "INVALID_NUMERIC_RANGE" => ResearchErrors.InvalidFile,
                "PREDICTION_ALIGNMENT_INVALID" or "PREDICTION_SOURCE_MISMATCH"
                    or "PREDICTION_INVALID" or "PREDICTION_INTEGRITY_FAILED" => ResearchErrors.ArtifactHashMismatch,
                _ when exception.Retryable => ResearchErrors.InferenceUnavailable,
                _ => ResearchErrors.EvaluationFailed
            };
            throw new BusinessException(errorCode).WithData("ServiceCode", exception.Code);
        }
        if (evaluation.ArtifactKind != "research" || evaluation.EvaluationProtocol != "whole-tumor-v1"
            || evaluation.ModelVersion != job.ModelSemanticVersion
            || evaluation.Architecture != job.Architecture.Value.ToString()
            || evaluation.PreprocessingVersion != job.PreprocessingVersion
            || evaluation.Threshold != job.Threshold
            || !string.Equals(evaluation.WeightSha256, job.WeightSha256, StringComparison.OrdinalIgnoreCase)
            || evaluation.RequestId != $"{job.Id:N}-{job.RetryCount}"
            || evaluation.CorrelationId != job.CorrelationId
            || !string.Equals(evaluation.InputSha256, job.InputSha256, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(evaluation.GroundTruthSha256, study.GroundTruthSha256,
                StringComparison.OrdinalIgnoreCase)
            || evaluation.PredictionObjectKey != result.RemotePredictionObjectKey
            || !string.Equals(evaluation.PredictionSha256, result.RemotePredictionSha256,
                StringComparison.OrdinalIgnoreCase))
            throw new BusinessException(ResearchErrors.ArtifactHashMismatch);

        result.RecordEvaluation(study.GroundTruthSha256, evaluation.EvaluationProtocol,
            evaluation.PatientMetrics.Dice, evaluation.PatientMetrics.Iou,
            evaluation.PatientMetrics.Precision, evaluation.PatientMetrics.Recall);
        await results.UpdateAsync(result, autoSave: true, cancellationToken: cancellationToken);
        return Map<SegmentationResult, SegmentationResultDto>(result);
    }
}
