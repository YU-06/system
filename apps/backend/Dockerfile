FROM mcr.microsoft.com/dotnet/sdk:10.0.400 AS build
WORKDIR /src
COPY global.json ./
COPY apps/backend/ apps/backend/
RUN dotnet restore apps/backend/src/BrainSeg.HttpApi.Host/BrainSeg.HttpApi.Host.csproj --locked-mode
RUN dotnet publish apps/backend/src/BrainSeg.HttpApi.Host/BrainSeg.HttpApi.Host.csproj --configuration Release --no-restore --output /out /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/ ./
RUN mkdir -p /app/data/objects && chown -R app:app /app/data
ENV ASPNETCORE_URLS=http://+:8080
USER app
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=12 CMD curl -fsS http://127.0.0.1:8080/health || exit 1
ENTRYPOINT ["dotnet", "BrainSeg.HttpApi.Host.dll"]