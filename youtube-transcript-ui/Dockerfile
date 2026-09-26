# YouTube Transcript UI - Dockerfile
# Multi-stage build for React frontend with Nginx

# =============================================================================
# Stage 1: Build stage
# =============================================================================
FROM node:24-alpine AS builder

# Set working directory
WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci

# Copy source files
COPY . .

# Optional API address, for serving the UI from a different address than the API.
# Empty by default: the UI calls /api on its own origin and nginx forwards it.
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL

# Build the application
RUN npm run build

# =============================================================================
# Stage 2: Production stage with Nginx
# =============================================================================
FROM nginx:alpine AS runtime

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/health || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
