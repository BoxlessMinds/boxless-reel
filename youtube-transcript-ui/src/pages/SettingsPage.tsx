import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { Loader2, Check, X, Eye, EyeOff, Key, Bot, Cog, Globe, ExternalLink, Youtube } from "lucide-react";
import { PageContainer } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { useSettingsContext } from "@/contexts/SettingsContext";
import { useValidateApiKey } from "@/hooks/useSettings";
import { useYoutubeAuthStatus, useConnectYoutube, useDisconnectYoutube } from "@/hooks/useYoutubeAuth";
import type { LLMSettingsUpdate } from "@/api/types";

export default function SettingsPage() {
  const { settings, isLoading, updateSettings } = useSettingsContext();
  const validateKeyMutation = useValidateApiKey();
  const [searchParams, setSearchParams] = useSearchParams();

  // YouTube connection state
  const { data: youtubeAuthStatus, isLoading: isYoutubeAuthLoading } = useYoutubeAuthStatus();
  const connectYoutubeMutation = useConnectYoutube();
  const disconnectYoutubeMutation = useDisconnectYoutube();

  // Show a success toast after the OAuth redirect and strip the query param
  useEffect(() => {
    if (searchParams.get("connected") === "1") {
      toast.success("YouTube account connected successfully");
      searchParams.delete("connected");
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const handleConnectYoutube = async () => {
    try {
      const result = await connectYoutubeMutation.mutateAsync();
      window.location.href = result.authorization_url;
    } catch {
      toast.error("Failed to start Google connection");
    }
  };

  const handleDisconnectYoutube = async () => {
    try {
      await disconnectYoutubeMutation.mutateAsync();
      toast.success("YouTube account disconnected");
    } catch {
      toast.error("Failed to disconnect YouTube account");
    }
  };

  // Form state
  const [anthropicKey, setAnthropicKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [showAnthropicKey, setShowAnthropicKey] = useState(false);
  const [showOpenaiKey, setShowOpenaiKey] = useState(false);
  const [defaultProvider, setDefaultProvider] = useState<"anthropic" | "openai">("anthropic");
  const [defaultModel, setDefaultModel] = useState("claude-sonnet-4-5");
  const [maxContextChunks, setMaxContextChunks] = useState(10);
  const [chunkSize, setChunkSize] = useState(1000);
  const [chunkOverlap, setChunkOverlap] = useState(200);

  // Web search state
  const [tavilyKey, setTavilyKey] = useState("");
  const [showTavilyKey, setShowTavilyKey] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(true);
  const [webSearchMaxResults, setWebSearchMaxResults] = useState(5);

  // Validation state
  const [anthropicValid, setAnthropicValid] = useState<boolean | null>(null);
  const [openaiValid, setOpenaiValid] = useState<boolean | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Initialize form from settings
  useEffect(() => {
    if (settings) {
      setDefaultProvider(settings.default_provider);
      setDefaultModel(settings.default_model);
      setMaxContextChunks(settings.max_context_chunks);
      setChunkSize(settings.chunk_size);
      setChunkOverlap(settings.chunk_overlap);
      setWebSearchEnabled(settings.web_search_enabled);
      setWebSearchMaxResults(settings.web_search_max_results);
    }
  }, [settings]);

  // Get models for selected provider
  const getModelsForProvider = (provider: "anthropic" | "openai") => {
    const providerModels = settings?.available_models.find(p => p.provider === provider);
    return providerModels?.models || [];
  };

  // Update default model when provider changes
  useEffect(() => {
    const models = getModelsForProvider(defaultProvider);
    if (models.length > 0 && !models.includes(defaultModel)) {
      setDefaultModel(models[0]);
    }
  }, [defaultProvider]);

  const handleValidateKey = async (provider: "anthropic" | "openai") => {
    const key = provider === "anthropic" ? anthropicKey : openaiKey;
    if (!key) {
      toast.error("Please enter an API key to validate");
      return;
    }

    try {
      const result = await validateKeyMutation.mutateAsync({ provider, apiKey: key });
      if (result.valid) {
        if (provider === "anthropic") {
          setAnthropicValid(true);
        } else {
          setOpenaiValid(true);
        }
        toast.success(`${provider === "anthropic" ? "Anthropic" : "OpenAI"} API key is valid`);
      } else {
        if (provider === "anthropic") {
          setAnthropicValid(false);
        } else {
          setOpenaiValid(false);
        }
        toast.error(result.error || "API key validation failed");
      }
    } catch {
      toast.error("Failed to validate API key");
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const update: LLMSettingsUpdate = {
        default_provider: defaultProvider,
        default_model: defaultModel,
        max_context_chunks: maxContextChunks,
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
        web_search_enabled: webSearchEnabled,
        web_search_max_results: webSearchMaxResults,
      };

      // Only include API keys if they were changed
      if (anthropicKey) {
        update.anthropic_api_key = anthropicKey;
      }
      if (openaiKey) {
        update.openai_api_key = openaiKey;
      }
      if (tavilyKey) {
        update.tavily_api_key = tavilyKey;
      }

      await updateSettings(update);
      toast.success("Settings saved successfully");

      // Clear the key inputs after save
      setAnthropicKey("");
      setOpenaiKey("");
      setTavilyKey("");
      setAnthropicValid(null);
      setOpenaiValid(null);
    } catch {
      toast.error("Failed to save settings");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <PageContainer>
        <div className="flex items-center justify-center py-24">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
          <p className="text-muted-foreground">
            Configure your LLM providers and agent behavior.
          </p>
        </div>

        {/* Connect YouTube Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Youtube className="h-5 w-5" />
              Connect YouTube
            </CardTitle>
            <CardDescription>
              Connect your Google account to enable YouTube playlist access.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {isYoutubeAuthLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : youtubeAuthStatus?.connected ? (
              <>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium">{youtubeAuthStatus.google_account_email}</p>
                    <p className="text-sm text-muted-foreground">Your YouTube account is connected.</p>
                  </div>
                  <Badge variant="secondary" className="bg-green-100 text-green-800">
                    Connected
                  </Badge>
                </div>
                <Button
                  variant="outline"
                  onClick={handleDisconnectYoutube}
                  disabled={disconnectYoutubeMutation.isPending}
                >
                  {disconnectYoutubeMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Disconnecting...
                    </>
                  ) : (
                    "Disconnect"
                  )}
                </Button>
              </>
            ) : (
              <Button onClick={handleConnectYoutube} disabled={connectYoutubeMutation.isPending}>
                {connectYoutubeMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Connecting...
                  </>
                ) : (
                  "Connect YouTube Account"
                )}
              </Button>
            )}
          </CardContent>
        </Card>

        {/* API Keys Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Key className="h-5 w-5" />
              LLM Providers
            </CardTitle>
            <CardDescription>
              Configure your API keys for Anthropic and OpenAI. Keys are encrypted before storage.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Anthropic */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label htmlFor="anthropic-key" className="text-base font-medium">
                  Anthropic API Key
                </Label>
                {settings?.anthropic_api_key_configured && (
                  <Badge variant="secondary" className="bg-green-100 text-green-800">
                    Configured
                  </Badge>
                )}
              </div>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    id="anthropic-key"
                    type={showAnthropicKey ? "text" : "password"}
                    placeholder={settings?.anthropic_api_key_configured ? "Enter new key to update..." : "sk-ant-..."}
                    value={anthropicKey}
                    onChange={(e) => {
                      setAnthropicKey(e.target.value);
                      setAnthropicValid(null);
                    }}
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowAnthropicKey(!showAnthropicKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showAnthropicKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <Button
                  variant="outline"
                  onClick={() => handleValidateKey("anthropic")}
                  disabled={!anthropicKey || validateKeyMutation.isPending}
                >
                  {validateKeyMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : anthropicValid === true ? (
                    <Check className="h-4 w-4 text-green-600" />
                  ) : anthropicValid === false ? (
                    <X className="h-4 w-4 text-red-600" />
                  ) : (
                    "Validate"
                  )}
                </Button>
              </div>
            </div>

            <Separator />

            {/* OpenAI */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label htmlFor="openai-key" className="text-base font-medium">
                  OpenAI API Key
                </Label>
                {settings?.openai_api_key_configured && (
                  <Badge variant="secondary" className="bg-green-100 text-green-800">
                    Configured
                  </Badge>
                )}
              </div>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    id="openai-key"
                    type={showOpenaiKey ? "text" : "password"}
                    placeholder={settings?.openai_api_key_configured ? "Enter new key to update..." : "sk-..."}
                    value={openaiKey}
                    onChange={(e) => {
                      setOpenaiKey(e.target.value);
                      setOpenaiValid(null);
                    }}
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowOpenaiKey(!showOpenaiKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showOpenaiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <Button
                  variant="outline"
                  onClick={() => handleValidateKey("openai")}
                  disabled={!openaiKey || validateKeyMutation.isPending}
                >
                  {validateKeyMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : openaiValid === true ? (
                    <Check className="h-4 w-4 text-green-600" />
                  ) : openaiValid === false ? (
                    <X className="h-4 w-4 text-red-600" />
                  ) : (
                    "Validate"
                  )}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Model Configuration Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="h-5 w-5" />
              Model Configuration
            </CardTitle>
            <CardDescription>
              Set your default LLM provider and model for chat interactions.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-6 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="default-provider">Default Provider</Label>
                <Select
                  value={defaultProvider}
                  onValueChange={(value: "anthropic" | "openai") => setDefaultProvider(value)}
                >
                  <SelectTrigger id="default-provider">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="anthropic">Anthropic</SelectItem>
                    <SelectItem value="openai">OpenAI</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="default-model">Default Model</Label>
                <Select
                  value={defaultModel}
                  onValueChange={setDefaultModel}
                >
                  <SelectTrigger id="default-model">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {getModelsForProvider(defaultProvider).map((model) => (
                      <SelectItem key={model} value={model}>
                        {model}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Agent Behavior Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Cog className="h-5 w-5" />
              Agent Behavior
            </CardTitle>
            <CardDescription>
              Fine-tune how the AI agent processes and retrieves transcript context.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-8">
            {/* Max Context Chunks */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-base">Max Context Chunks</Label>
                  <p className="text-sm text-muted-foreground">
                    Maximum number of transcript chunks included in context
                  </p>
                </div>
                <span className="font-mono text-sm font-medium">{maxContextChunks}</span>
              </div>
              <Slider
                value={[maxContextChunks]}
                onValueChange={([value]) => setMaxContextChunks(value)}
                min={1}
                max={50}
                step={1}
              />
            </div>

            {/* Chunk Size */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-base">Chunk Size</Label>
                  <p className="text-sm text-muted-foreground">
                    Target size for transcript text chunks (characters)
                  </p>
                </div>
                <span className="font-mono text-sm font-medium">{chunkSize}</span>
              </div>
              <Slider
                value={[chunkSize]}
                onValueChange={([value]) => setChunkSize(value)}
                min={100}
                max={5000}
                step={100}
              />
            </div>

            {/* Chunk Overlap */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-base">Chunk Overlap</Label>
                  <p className="text-sm text-muted-foreground">
                    Overlap between consecutive chunks (characters)
                  </p>
                </div>
                <span className="font-mono text-sm font-medium">{chunkOverlap}</span>
              </div>
              <Slider
                value={[chunkOverlap]}
                onValueChange={([value]) => setChunkOverlap(value)}
                min={0}
                max={500}
                step={50}
              />
            </div>
          </CardContent>
        </Card>

        {/* Web Search Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Globe className="h-5 w-5" />
              Web Search
            </CardTitle>
            <CardDescription>
              Enable web search to supplement transcript context with real-time information from the internet.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Enable/Disable Toggle */}
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label className="text-base">Enable Web Search</Label>
                <p className="text-sm text-muted-foreground">
                  Allow the AI to search the web for additional context
                </p>
              </div>
              <Switch
                checked={webSearchEnabled}
                onCheckedChange={setWebSearchEnabled}
              />
            </div>

            <Separator />

            {/* Tavily API Key */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label htmlFor="tavily-key" className="text-base font-medium">
                  Tavily API Key
                </Label>
                {settings?.tavily_api_key_configured && (
                  <Badge variant="secondary" className="bg-green-100 text-green-800">
                    Configured
                  </Badge>
                )}
              </div>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    id="tavily-key"
                    type={showTavilyKey ? "text" : "password"}
                    placeholder={settings?.tavily_api_key_configured ? "Enter new key to update..." : "tvly-..."}
                    value={tavilyKey}
                    onChange={(e) => setTavilyKey(e.target.value)}
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowTavilyKey(!showTavilyKey)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showTavilyKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                Get your API key at{" "}
                <a
                  href="https://tavily.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline inline-flex items-center gap-1"
                >
                  tavily.com
                  <ExternalLink className="h-3 w-3" />
                </a>
              </p>
            </div>

            <Separator />

            {/* Max Results */}
            <div className="space-y-2">
              <Label htmlFor="web-search-max-results">Max Search Results</Label>
              <Select
                value={String(webSearchMaxResults)}
                onValueChange={(value) => setWebSearchMaxResults(Number(value))}
              >
                <SelectTrigger id="web-search-max-results" className="w-[120px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="3">3</SelectItem>
                  <SelectItem value="5">5</SelectItem>
                  <SelectItem value="7">7</SelectItem>
                  <SelectItem value="10">10</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-sm text-muted-foreground">
                Maximum number of web search results to include in context
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Save Button */}
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={isSaving} size="lg">
            {isSaving ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              "Save Settings"
            )}
          </Button>
        </div>
      </div>
    </PageContainer>
  );
}
