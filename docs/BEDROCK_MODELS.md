# Choosing the Amazon Bedrock models

The application uses two Bedrock models:

| Role | Model | Your choice? |
|---|---|---|
| **Embeddings**: turn text into vectors for search | Amazon **Titan Text Embeddings V2** (`amazon.titan-embed-text-v2:0`) | **No.** The database stores 1024-dimension vectors, and the code requests exactly that from Titan V2. Another embedding model would need code changes, a migration and reprocessing every document. Just enable it. |
| **Chat**: categorize, summarize and answer questions | Any model that supports Bedrock's **Converse** API | **Yes**, set with `BEDROCK_CHAT_MODEL_ID`. It can be changed at any time; documents do not need reprocessing. |

## 1. What the chat model does here

| Task | Size | Output ceiling (`maxTokens`, includes the model's thinking) |
|---|---|---|
| Categorize a new document | up to ~3,000 words in, a few words out | 1,024 |
| Propose a summary for HR review | up to ~6,000 words in, three sentences out | 2,048 |
| Answer an employee question from ~5 retrieved sections | ~2,000 tokens in, ~300 out | 4,096 |

Requirements that follow from this:

- **Speed:** API Gateway ends requests after **30 seconds**, so answers must be well within that.
- **Faithfulness:** amounts, limits and deadlines must be quoted exactly from the evidence.
- **Cost per question:** questions are frequent and small.

## 2. Recommendation

| Model | Fit for this app |
|---|---|
| **Claude Haiku 5.5** | **Start here.** Fast and the lowest cost; well suited to answering from a handful of retrieved sections and to the short categorize/summarize tasks. |
| **Claude Sonnet 5.5** | Upgrade if answers miss nuance across several sections, or summaries need more care. |
| Claude Opus 5.5 | More capable than this task needs, and slower, which leaves less margin under the 30-second limit. |

Bedrock prices are set by AWS and differ from Anthropic's own: see [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/). As a rough guide, a question costs a fraction of a cent on Haiku and about ten to twenty times more on Sonnet. Thinking adds output tokens on top.

## 3. Enable the models

In the AWS console, in the region you will deploy to, open **Amazon Bedrock → Model access**. Enable **Titan Text Embeddings V2** and the chat model you chose. Approval is immediate for most models.

## 4. Find the exact model ID

Model IDs differ by region and change with new versions, so look them up instead of copying one from somewhere else:

```bash
# Claude models in this region, and how each can be called
aws bedrock list-foundation-models --by-provider anthropic \
  --query 'modelSummaries[].[modelId, modelName, join(`,`, inferenceTypesSupported)]' --output table

# Inference profiles (newer models are usually callable only through one)
aws bedrock list-inference-profiles \
  --query "inferenceProfileSummaries[?contains(inferenceProfileId, 'anthropic')].[inferenceProfileId, inferenceProfileName]" \
  --output table
```

- The model lists only **INFERENCE_PROFILE**: use its **inference profile ID** (usually starting with a geography prefix such as `us.` or `eu.`).
- The model lists **ON_DEMAND**: its model ID works directly.

```bash
export MODEL_ID=<the inference profile ID or model ID>
```

## 5. Test the models the way the application calls them

**Chat model.** Same settings as the app: no temperature, and a 4,096-token ceiling:

```bash
aws bedrock-runtime converse --model-id "$MODEL_ID" \
  --messages '[{"role":"user","content":[{"text":"Reply with OK"}]}]' \
  --inference-config maxTokens=4096 \
  --query 'output.message.content[?text].text' --output text       # prints OK
```

**Embedding model:**

```bash
aws bedrock-runtime invoke-model --model-id amazon.titan-embed-text-v2:0 \
  --body '{"inputText":"hello","dimensions":1024,"normalize":true}' \
  --cli-binary-format raw-in-base64-out /tmp/embedding.json >/dev/null && head -c 60 /tmp/embedding.json; echo
# prints {"embedding":[...
```

| Error | Meaning |
|---|---|
| `AccessDeniedException` | Model access is not enabled in this region (step 3) |
| `ValidationException` mentioning on-demand throughput or an inference profile | Use the inference profile ID (step 4) |
| `ResourceNotFoundException` | The ID is wrong or not offered in this region |

## 6. Configure it

| How you run the app | Setting |
|---|---|
| Locally with Bedrock | `AI_PROVIDER=bedrock` and `BEDROCK_CHAT_MODEL_ID` in `.env` |
| Command-line deployment | `bedrock_chat_model_id` in `infrastructure/terraform/terraform.tfvars` |
| GitHub Actions deployment | The `BEDROCK_CHAT_MODEL_ID` repository variable |

## 7. Optional: lower effort for faster, cheaper answers

Current Claude models think before answering. Their **effort** setting trades depth for speed and cost, and `low` is often enough for categorizing and for answering from retrieved evidence. The application can pass it through Bedrock, but only enable it after this check succeeds with your model:

```bash
aws bedrock-runtime converse --model-id "$MODEL_ID" \
  --messages '[{"role":"user","content":[{"text":"Reply with OK"}]}]' \
  --inference-config maxTokens=4096 \
  --additional-model-request-fields '{"output_config":{"effort":"low"}}' \
  --query 'output.message.content[?text].text' --output text       # prints OK
```

If it prints `OK`, set it where you configure the app: `BEDROCK_EFFORT=low` in `.env`, `bedrock_effort = "low"` in `terraform.tfvars`, or a `BEDROCK_EFFORT` repository variable with the value `low` for GitHub Actions deployments. If it returns a validation error, leave the setting empty and the model uses its default.

> **Using a non-Claude model** (for example Amazon Nova)? Leave `BEDROCK_EFFORT` empty, since effort is a Claude setting. If you want a sampling temperature, set `BEDROCK_TEMPERATURE` (current Claude models reject it).

## 8. Check it in the running app

The API and workers log one line per model call. Look for `"event": "bedrock.converse"` with the token counts and `stop_reason`. A `bedrock.truncated` warning means a reply hit its ceiling; lowering effort, or reporting it as an issue, are the fixes.

```bash
aws logs tail /ecs/hrflow-dev/api --since 15m | grep bedrock     # AWS deployment
docker compose logs backend | grep bedrock                       # local
```
