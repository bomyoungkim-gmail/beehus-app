FROM node:20-alpine

WORKDIR /app

# Copy package files first for caching
COPY package*.json ./

# Install dependencies in the Linux environment
RUN npm install

# Copy the rest of the app
COPY . .

# Expose port
EXPOSE 5173

# Start command
CMD ["npm", "run", "dev", "--", "--host"]
