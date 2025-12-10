FROM nginx:alpine

# Remove default nginx configuration
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/ /etc/nginx/conf.d/

# Create directory for certificates
RUN mkdir -p /etc/nginx/certs

# Expose ports
EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]