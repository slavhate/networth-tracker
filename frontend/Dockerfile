# Build stage
FROM node:20-alpine as build

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# Production stage with nginx
FROM nginx:alpine

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets with correct permissions
COPY --from=build /app/dist /usr/share/nginx/html
RUN chmod -R 755 /usr/share/nginx/html

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
